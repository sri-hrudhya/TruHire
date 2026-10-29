import logging
import math
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    Position, User, DEFAULT_DEMAND_NAMES, canonical_demand_id, demand_display_id, Candidate, CandidateMatch, SearchState, Conversation, EmailRecord,
    CandidateAssignment, CandidateComment, RequirementCandidateStatus, REQUIREMENT_STATUSES, DEFAULT_REQUIREMENT_STATUS, get_next_position_display_id,
    JD_STATUSES, LEGACY_JD_STATUS_ALIASES, DEFAULT_JD_STATUS, CLIENT_NAMES, RESUME_LINKED_JD_STATUSES, MAX_CANCELLATION_REASON_CHARS, HISTORY_ACTIONS, HISTORY_CREATED, HISTORY_UPDATED, HISTORY_DELETED, HISTORY_STATUS_CHANGED, RequirementHistory,
)
from backend.auth import get_current_user
from backend.config import settings
from backend.services.common import requirement_history as history
from backend.services.common.cache import get_cache, set_cache, delete_cache, clear_cache, get_index_epoch
from backend.services.classification import classify_jd_detailed
from backend.services.ingestion.parsing import extract_text_from_file, is_supported_jd_file
from backend.services.ingestion.storage import resolve_stored_file, save_upload_file
from backend.services.llm.ai_service import summarize_jd
from backend.services.retrieval.filters import extract_jd_filters

logger = logging.getLogger(__name__)

router = APIRouter(tags=["job-descriptions"])


MAX_DETAIL_CHARS = 200
MAX_EXPERIENCE_YEARS = 60
MAX_LOCATIONS = 10
MAX_POSITIONS = 10_000


def _check_experience_range(low: Optional[float], high: Optional[float]) -> None:
    if low is not None and high is not None and high < low:
        raise ValueError("Max experience cannot be less than min experience.")


class JDDetails(BaseModel):
    """Recruiter-entered JD fields shared by create and update. Blank text means "not stated"."""
    role: Optional[str] = Field(default=None, max_length=MAX_DETAIL_CHARS)
    location: Optional[str] = Field(default=None, max_length=MAX_DETAIL_CHARS * MAX_LOCATIONS)  # legacy single value; derived from `locations`
    locations: Optional[List[str]] = None
    no_of_positions: Optional[int] = Field(default=None, ge=1, le=MAX_POSITIONS)
    client_name: Optional[str] = Field(default=None, max_length=MAX_DETAIL_CHARS)
    experience_years: Optional[float] = Field(default=None, ge=0, le=MAX_EXPERIENCE_YEARS)  # minimum
    experience_max_years: Optional[float] = Field(default=None, ge=0, le=MAX_EXPERIENCE_YEARS)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    # Companion data of a status: why a demand was Cancelled, which resumes a Mapped / Fulfilled one was filled with.
    cancellation_reason: Optional[str] = Field(default=None, max_length=MAX_CANCELLATION_REASON_CHARS)
    candidate_ids: Optional[List[str]] = None

    @field_validator("role", "location", "client_name", "cancellation_reason", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be text")
        return value.strip() or None

    @model_validator(mode="before")
    @classmethod
    def _single_location_to_list(cls, data):
        # Older clients send one `location`; it becomes a one-item `locations`.
        if isinstance(data, dict) and "locations" not in data and "location" in data:
            return {**data, "locations": [data["location"]] if isinstance(data["location"], str) and data["location"].strip() else []}
        return data

    @field_validator("locations", mode="before")
    @classmethod
    def _clean_locations(cls, value):
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
            raise ValueError("must be a list of places")
        places: List[str] = []
        for raw in value:
            place = " ".join(raw.split())
            if not place:
                continue
            if len(place) > MAX_DETAIL_CHARS:
                raise ValueError(f"each location is limited to {MAX_DETAIL_CHARS} characters")
            if place.lower() not in {p.lower() for p in places}:
                places.append(place)
        if len(places) > MAX_LOCATIONS:
            raise ValueError(f"at most {MAX_LOCATIONS} locations")
        return places

    @model_validator(mode="after")
    def _experience_range(self):
        _check_experience_range(self.experience_years, self.experience_max_years)
        if self.locations is not None:  # keep the joined text in step; assigning also marks `location` as sent
            self.location = "; ".join(self.locations) or None
        return self

    @field_validator("client_name")
    @classmethod
    def _canonical_client(cls, value):
        # A known client is stored with its canonical spelling; anything else is the typed "Others" name.
        if value is None:
            return None
        return next((c for c in CLIENT_NAMES if c.lower() == value.lower()), value)

    @field_validator("status", mode="before")
    @classmethod
    def _alias_status(cls, value):
        return LEGACY_JD_STATUS_ALIASES.get(value, value)

    @field_validator("status")
    @classmethod
    def _known_status(cls, value):
        if value is not None and value not in JD_STATUSES:
            raise ValueError(f"must be one of: {', '.join(JD_STATUSES)}")
        return value

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class PositionCreateRequest(JDDetails):
    title: str
    jd_text: str
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    demand_id: Optional[str] = None  # the folder the recruiter chose; omitted (API callers) = auto-classified


class PositionUpdateRequest(JDDetails):
    demand_id: Optional[str] = None  # omitted = folder unchanged; edits never re-classify
    title: Optional[str] = None
    jd_text: Optional[str] = None
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_id: Optional[str] = None
    title: str
    jd_text: str
    jd_summary: Optional[str] = None
    jd_version: int
    created_by: str
    created_at: datetime
    file_url: Optional[str] = None
    original_filename: Optional[str] = None
    demand_id: Optional[str] = None
    status: str = DEFAULT_JD_STATUS
    role: Optional[str] = None
    location: Optional[str] = None
    locations: List[str] = []
    no_of_positions: Optional[int] = None
    client_name: Optional[str] = None
    experience_years: Optional[float] = None
    experience_max_years: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    updated_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None  # updated_at, or the creation time for a demand never edited
    last_modified_by: Optional[str] = None  # name of whoever last changed it, or the creator for a demand never edited
    cancellation_reason: Optional[str] = None  # Cancelled demands only
    mapped_resumes: List[Dict[str, Any]] = []  # Mapped / Fulfilled demands only: [{id, display_id, candidate_name}]
    created_by_name: Optional[str] = None
    classification_note: Optional[str] = None  # set when the category was uncertain and defaulted to Others

    @field_validator("locations", mode="before")
    @classmethod
    def _coerce_locations(cls, v, info: ValidationInfo):
        if v is not None:
            return v
        loc = info.data.get("location") if info.data else None
        if loc and isinstance(loc, str):
            return [p.strip() for p in loc.split(";") if p.strip()]
        return []

    @field_validator("mapped_resumes", mode="before")
    @classmethod
    def _coerce_mapped_resumes(cls, v):
        return v if v is not None else []


class RequirementStatusRequest(BaseModel):
    status: str


class JDStatusRequest(BaseModel):
    status: str
    cancellation_reason: Optional[str] = Field(default=None, max_length=MAX_CANCELLATION_REASON_CHARS)
    candidate_ids: Optional[List[str]] = None


class PositionDemandRequest(BaseModel):
    demand_id: Optional[str] = None  # null re-runs automatic classification


class JDExtractResponse(BaseModel):
    title: str
    jd_text: str
    original_filename: str
    file_url: str
    category: Optional[str] = None
    classification_note: Optional[str] = None
    # Details the JD text itself states; null where it does not, so the form leaves them blank.
    detected_title: Optional[str] = None
    location: Optional[str] = None
    experience_years: Optional[float] = None
    suggested_demand_id: Optional[str] = None


class JDDetailsRequest(BaseModel):
    title: str = Field(default="", max_length=500)
    jd_text: str = Field(max_length=200_000)


class JDDetectedDetails(BaseModel):
    detected_title: Optional[str] = None
    location: Optional[str] = None
    experience_years: Optional[float] = None
    suggested_demand_id: Optional[str] = None  # the classifier's confident guess, preselected in the folder dropdown


def _classify_position(pos: Position) -> None:
    """Auto-assign pos.demand_id from its content; used on create when the caller chose no folder."""
    result = classify_jd_detailed(pos.title, pos.jd_text)
    pos.demand_id = canonical_demand_id(result.category)
    pos.classification_note = result.note  # transient: surfaced in the response only


def _checked_demand_id(demand_id: str) -> str:
    if demand_id not in {canonical_demand_id(n) for n in DEFAULT_DEMAND_NAMES}:
        raise HTTPException(422, "Choose one of: " + ", ".join(DEFAULT_DEMAND_NAMES) + ".")
    return demand_id


def invalidate_requirements_cache(jd_id: Optional[str] = None):
    delete_cache("requirements:list")
    clear_cache("truhire:site:jds:")
    clear_cache("search:")
    # Email history shows live requirement titles/deletion state.
    clear_cache("email:history:")
    if jd_id:
        delete_cache(f"requirements:detail:{jd_id}")
        clear_cache(f"requirements:matches:{jd_id}")


TRACKED_FIELDS = ("title", "jd_text", "role", "experience_years", "experience_max_years", "no_of_positions", "start_date", "end_date", "location", "client_name", "status", "demand_id", "cancellation_reason", "mapped_candidate_ids")
_TEXT_PREVIEW_CHARS = 300


def _demand_name(demand_id: Optional[str]) -> Optional[str]:
    """'TRU-DM-01 · Java' for the history log; None stays None."""
    name = next((n for n in DEFAULT_DEMAND_NAMES if canonical_demand_id(n) == demand_id), None)
    return f"{demand_display_id(demand_id)} · {name}" if name else demand_id


def _clip(text: Optional[str]) -> Optional[str]:
    return text if not text or len(text) <= _TEXT_PREVIEW_CHARS else text[:_TEXT_PREVIEW_CHARS] + "…"


def _snapshot(pos: Position) -> dict:
    snap = history.snapshot(pos, TRACKED_FIELDS)
    snap["status"] = LEGACY_JD_STATUS_ALIASES.get(snap["status"], snap["status"]) or DEFAULT_JD_STATUS
    snap["mapped_candidate_ids"] = ",".join(sorted(pos.mapped_candidate_ids or [])) or None
    return snap


def _resume_labels(db: Optional[Session], joined: Optional[str]) -> Optional[str]:
    """'TRU-CN-0001 Asha Rao, TRU-CN-0002 …' for the history log from a comma-joined id list."""
    ids = [i for i in (joined or "").split(",") if i]
    if not ids or db is None:
        return joined
    found = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(ids)).all()}
    return ", ".join(f"{found[i].display_id} {found[i].candidate_name}" if i in found else i for i in ids)


def _readable(changes: dict, db: Optional[Session] = None) -> dict:
    """History view of a diff: demand shown by name instead of id, long specification text shortened."""
    out = {}
    for field, delta in changes.items():
        if field == "demand_id":
            out["demand"] = {"old": _demand_name(delta["old"]), "new": _demand_name(delta["new"])}
        elif field == "mapped_candidate_ids":
            out["mapped_resumes"] = {"old": _resume_labels(db, delta["old"]), "new": _resume_labels(db, delta["new"])}
        elif field == "jd_text":
            out[field] = {"old": _clip(delta["old"]), "new": _clip(delta["new"])}
        else:
            out[field] = delta
    return out


def _stated_experience(jd_text: str) -> Optional[float]:
    """Years of experience only when the JD text states them (no default guess)."""
    from backend.services.ingestion.parsing import YEARS_EXP_PATTERN
    nums = [float(m) for m in YEARS_EXP_PATTERN.findall(jd_text or "")]
    return max(nums) if nums else None


def _detect_details(title: str, jd_text: str) -> dict:
    """Title, location and experience as the JD text states them (None where it does not).

    Reuses extract_jd_filters (LLM, then heuristics); the role only counts as a title when it was
    read from the JD text, never when it merely echoes the supplied title.
    """
    guess = classify_jd_detailed(title, jd_text)
    out = {
        "detected_title": None, "location": None, "experience_years": _stated_experience(jd_text),
        "suggested_demand_id": canonical_demand_id(guess.category) if guess.confident else None,
    }
    if out["experience_years"] is not None and not 0 <= out["experience_years"] <= MAX_EXPERIENCE_YEARS:
        out["experience_years"] = None
    try:
        found = extract_jd_filters(title, jd_text)
    except Exception as exc:  # the form still works with every field blank
        logger.warning("JD detail extraction failed: %s", exc)
        return out
    sources = found.get("sources") or {}
    location = (found.get("location") or "").strip()
    role = (found.get("role") or "").strip()
    out["location"] = location[:MAX_DETAIL_CHARS] or None
    if role and sources.get("role") == "jd_text":
        out["detected_title"] = role[:MAX_DETAIL_CHARS]
    return out


def _is_status(pos: Position, *statuses: str) -> bool:
    return (LEGACY_JD_STATUS_ALIASES.get(pos.status, pos.status) or DEFAULT_JD_STATUS) in statuses


def _mapped_resumes(ids: Optional[List[str]], candidates: Dict[str, Candidate]) -> List[dict]:
    """Resumes a demand was filled with; ones deleted since then are skipped rather than failing the page."""
    return [{"id": c.id, "display_id": c.display_id, "candidate_name": c.candidate_name}
            for c in (candidates.get(i) for i in ids or []) if c]


def _serialize_position(pos: Position, creator_name: Optional[str] = None, modifier_name: Optional[str] = None,
                        candidates: Optional[Dict[str, Candidate]] = None) -> dict:
    # JDs created before these fields existed fall back to what the JD itself states (already
    # extracted and cached in search_filters; no model call here), so older cards are not blank.
    derived = pos.search_filters or {}
    experience = pos.experience_years if pos.experience_years is not None else _stated_experience(pos.jd_text)
    return {
        "id": pos.id,
        "display_id": pos.display_id,
        "title": pos.title,
        "jd_text": pos.jd_text,
        "jd_summary": pos.jd_summary,
        "jd_version": pos.jd_version,
        "created_by": pos.created_by,
        "created_by_name": creator_name,
        "created_at": pos.created_at.isoformat() if pos.created_at else None,
        "file_url": pos.file_url,
        "original_filename": pos.original_filename,
        "demand_id": pos.demand_id,
        "status": LEGACY_JD_STATUS_ALIASES.get(pos.status, pos.status) or DEFAULT_JD_STATUS,
        "role": pos.role or derived.get("role"),
        "location": pos.location or derived.get("location"),
        "locations": pos.locations if pos.locations is not None else [p for p in [pos.location or derived.get("location")] if p],
        "no_of_positions": pos.no_of_positions,
        "client_name": pos.client_name,
        "updated_at": pos.updated_at.isoformat() if pos.updated_at else None,
        "last_modified_at": (pos.updated_at or pos.created_at).isoformat() if (pos.updated_at or pos.created_at) else None,
        "last_modified_by": modifier_name or creator_name,
        "cancellation_reason": pos.cancellation_reason if _is_status(pos, "Cancelled") else None,
        "mapped_resumes": _mapped_resumes(pos.mapped_candidate_ids, candidates or {}) if _is_status(pos, *RESUME_LINKED_JD_STATUSES) else [],
        "experience_years": experience,
        "experience_max_years": pos.experience_max_years,
        "start_date": pos.start_date.isoformat() if pos.start_date else None,
        "end_date": pos.end_date.isoformat() if pos.end_date else None,
    }


def list_jds(db: Session):
    cache_key = "requirements:list"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    positions = db.query(Position).order_by(Position.created_at.desc()).all()
    names = dict(db.query(User.id, User.name).all())
    wanted = {i for p in positions for i in p.mapped_candidate_ids or []}
    candidates = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(wanted)).all()} if wanted else {}
    data = [_serialize_position(p, names.get(p.created_by), names.get(p.updated_by), candidates) for p in positions]
    set_cache(cache_key, data, ttl_seconds=settings.CACHE_TTL_QUERY)
    return data


def _checked_jd_file_url(file_url: Optional[str]) -> Optional[str]:
    # file_url round-trips through the client (extract-text -> create), so only accept
    # references to a file that actually exists in JD storage.
    if not file_url:
        return None
    if not file_url.startswith("/uploads/job_descriptions/") or not resolve_stored_file(file_url):
        raise HTTPException(400, "Invalid requirement file reference.")
    return file_url


def create_jd(req: PositionCreateRequest, db: Session, user: User) -> Position:
    if not req.title.strip() or not req.jd_text.strip():
        raise HTTPException(400, "Title and requirement text cannot be blank.")
    display_id = get_next_position_display_id(db)
    pos = Position(
        display_id=display_id,
        title=req.title.strip(),
        jd_text=req.jd_text.strip(),
        jd_version=1,
        created_by=user.id,
        created_at=datetime.utcnow(),
        file_url=_checked_jd_file_url(req.file_url),
        original_filename=req.original_filename,
        status=DEFAULT_JD_STATUS,
        role=req.role, location=req.location, locations=req.locations or None, no_of_positions=req.no_of_positions or 1,
        client_name=req.client_name, experience_years=req.experience_years,
        experience_max_years=req.experience_max_years, start_date=req.start_date, end_date=req.end_date,
    )
    if req.demand_id:
        pos.demand_id = _checked_demand_id(req.demand_id)
    else:
        _classify_position(pos)
    db.add(pos)
    db.flush()
    if req.status and req.status != DEFAULT_JD_STATUS:
        _apply_status(db, pos, req.status, req.cancellation_reason, req.candidate_ids)
    stated = {k: v for k, v in _snapshot(pos).items() if v is not None}
    history.record(db, HISTORY_CREATED, pos, user, _readable(history.diff({}, stated)))
    db.commit()
    db.refresh(pos)
    invalidate_requirements_cache()
    return _with_creator(pos, user.name, db)


def _with_creator(pos: Position, name: Optional[str], db: Optional[Session] = None) -> Position:
    # Transient attributes: only the response carries them.
    pos.created_by_name = name
    pos.last_modified_at = pos.updated_at or pos.created_at
    pos.last_modified_by = (db.query(User.name).filter(User.id == pos.updated_by).scalar() if db and pos.updated_by else None) or name
    candidates = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(pos.mapped_candidate_ids)).all()} if db and pos.mapped_candidate_ids else {}
    pos.mapped_resumes = _mapped_resumes(pos.mapped_candidate_ids, candidates) if _is_status(pos, *RESUME_LINKED_JD_STATUSES) else []
    return pos


def _creator_name(pos: Position, db: Session) -> Optional[str]:
    return db.query(User.name).filter(User.id == pos.created_by).scalar()


def _touch(pos: Position, user: Optional[User]) -> None:
    """Stamp a save: when, and by whom (kept as is when the caller is unknown)."""
    pos.updated_at = datetime.utcnow()
    if user is not None:
        pos.updated_by = user.id


def _apply_status(db: Session, pos: Position, status: str, reason: Optional[str], candidate_ids: Optional[List[str]]) -> bool:
    """Set the status together with the data it needs; True if anything changed.

    Cancelled needs a reason; Mapped and Fulfilled need at least one existing resume. A status
    that is kept (e.g. Mapped -> Fulfilled) reuses what is already stored when nothing new is sent.
    Moving to any other status clears the companion data, so a reason or resume list never outlives its status.
    """
    current = _snapshot(pos)["status"]
    if status == current and not reason and candidate_ids is None:
        return False  # same status, nothing new sent: leave what is stored (older rows may have no reason / resumes)
    new_reason, new_ids = None, None
    if status == "Cancelled":
        new_reason = (reason or "").strip() or (pos.cancellation_reason if current == "Cancelled" else None)
        if not new_reason:
            raise HTTPException(422, "A cancellation reason is required.")
    elif status in RESUME_LINKED_JD_STATUSES:
        if candidate_ids is not None:
            ids = list(dict.fromkeys(candidate_ids))
        else:
            ids = list(pos.mapped_candidate_ids or []) if current in RESUME_LINKED_JD_STATUSES else []
        if not ids:
            raise HTTPException(422, f"Select at least one resume for a {status} demand.")
        found = {i for (i,) in db.query(Candidate.id).filter(Candidate.id.in_(ids)).all()}
        if len(found) != len(ids):
            raise HTTPException(422, "One or more selected resumes no longer exist.")
        new_ids = ids
    changed = (current, pos.cancellation_reason, pos.mapped_candidate_ids or None) != (status, new_reason, new_ids)
    pos.status, pos.cancellation_reason, pos.mapped_candidate_ids = status, new_reason, new_ids
    return changed


def get_jd(jd_id: str, db: Session) -> Position:
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(404, "Requirement not found.")
    return pos


def update_jd(jd_id: str, req: PositionUpdateRequest, db: Session, user: Optional[User] = None) -> Position:
    pos = get_jd(jd_id, db)
    before = _snapshot(pos)
    changed = False
    if req.title and req.title.strip() != pos.title:
        pos.title = req.title.strip()
        changed = True
    if req.jd_text and req.jd_text.strip() != pos.jd_text:
        pos.jd_text = req.jd_text.strip()
        pos.jd_version += 1
        pos.jd_summary = None
        changed = True
    if req.file_url is not None:
        pos.file_url = _checked_jd_file_url(req.file_url)
        changed = True
    if req.original_filename is not None:
        pos.original_filename = req.original_filename
        changed = True
    # Detail fields: a field the client sent (even as null) is applied, so a value can be cleared.
    for field in ("role", "location", "locations", "no_of_positions", "client_name", "experience_years", "experience_max_years", "start_date", "end_date"):
        if field not in req.model_fields_set:
            continue
        value = getattr(req, field)
        if field == "locations":
            value = value or None  # an empty list clears it
        if value != getattr(pos, field):
            setattr(pos, field, value)
            changed = True
    if pos.experience_years is not None and pos.experience_max_years is not None and pos.experience_max_years < pos.experience_years:
        db.rollback()
        raise HTTPException(422, "Max experience cannot be less than min experience.")
    if req.status is not None and _apply_status(db, pos, req.status, req.cancellation_reason, req.candidate_ids):
        changed = True
    if pos.start_date and pos.end_date and pos.end_date < pos.start_date:
        db.rollback()
        raise HTTPException(422, "End date cannot be before start date.")
    if req.demand_id and req.demand_id != pos.demand_id:
        pos.demand_id = _checked_demand_id(req.demand_id)  # the recruiter's choice; content edits never move a demand
        changed = True
    if changed:
        _touch(pos, user)
        _record_changes(db, pos, before, user)
        db.commit()
        db.refresh(pos)
        invalidate_requirements_cache(pos.id)
    return _with_creator(pos, _creator_name(pos, db), db)


def _record_changes(db: Session, pos: Position, before: dict, user: Optional[User]) -> None:
    """One 'status_changed' entry for a status change and one 'updated' entry for everything else."""
    changes = _readable(history.diff(before, _snapshot(pos)), db)
    status = changes.pop("status", None)
    if status:
        # The reason / resumes a status came with belong to that status change.
        companions = {k: changes.pop(k) for k in ("cancellation_reason", "mapped_resumes") if k in changes}
        history.record(db, HISTORY_STATUS_CHANGED, pos, user, {"status": status, **companions})
    if changes:
        history.record(db, HISTORY_UPDATED, pos, user, changes)


def set_jd_status(jd_id: str, status: str, db: Session, user: User, reason: Optional[str] = None,
                  candidate_ids: Optional[List[str]] = None) -> Position:
    status = LEGACY_JD_STATUS_ALIASES.get(status, status)
    if status not in JD_STATUSES:
        raise HTTPException(400, f"Invalid status. Use one of: {', '.join(JD_STATUSES)}.")
    pos = get_jd(jd_id, db)
    before = _snapshot(pos)
    if _apply_status(db, pos, status, (reason or "").strip() or None, candidate_ids):
        _touch(pos, user)
        _record_changes(db, pos, before, user)
        db.commit()
        db.refresh(pos)
        invalidate_requirements_cache(pos.id)
    return _with_creator(pos, _creator_name(pos, db), db)


def set_jd_demand(jd_id: str, demand_id: Optional[str], db: Session, user: Optional[User] = None) -> Position:
    """Move a requirement to one of the five categories (None = re-run automatic classification).
    Not a content edit: no version bump, so existing match scores stay valid. A later content edit
    re-classifies, so this is a correction, not a permanent override."""
    pos = get_jd(jd_id, db)
    if demand_id:
        if demand_id not in {canonical_demand_id(n) for n in DEFAULT_DEMAND_NAMES}:
            raise HTTPException(404, "Demand not found.")
        target = demand_id
    else:
        target = canonical_demand_id(classify_jd_detailed(pos.title, pos.jd_text).category)
    if pos.demand_id != target:
        before = _snapshot(pos)
        pos.demand_id = target
        _touch(pos, user)
        _record_changes(db, pos, before, user)
        db.commit()
        db.refresh(pos)
        delete_cache("requirements:list")
        delete_cache(f"requirements:detail:{pos.id}")
    return _with_creator(pos, _creator_name(pos, db), db)


def delete_jd(jd_id: str, db: Session, user: Optional[User] = None) -> dict:
    pos = get_jd(jd_id, db)
    display_id = pos.display_id
    last = {k: v for k, v in _snapshot(pos).items() if v is not None}
    history.record(db, HISTORY_DELETED, pos, user, _readable({k: {"old": v, "new": None} for k, v in last.items()}))
    # Delete associated CandidateMatch rows for this requirement
    db.query(CandidateMatch).filter(CandidateMatch.position_id == jd_id).delete(synchronize_session=False)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.position_id == jd_id).delete(synchronize_session=False)
    db.query(CandidateAssignment).filter(CandidateAssignment.position_id == jd_id).delete(synchronize_session=False)
    db.query(CandidateComment).filter(CandidateComment.position_id == jd_id).delete(synchronize_session=False)
    # Clear position_id from search states and conversations
    db.query(SearchState).filter(SearchState.position_id == jd_id).update({"position_id": None}, synchronize_session=False)
    db.query(Conversation).filter(Conversation.position_id == jd_id).update({"position_id": None}, synchronize_session=False)
    # Candidate records and resume documents are PRESERVED and NOT deleted!
    db.delete(pos)
    db.commit()
    invalidate_requirements_cache(jd_id)
    return {"deleted": 1, "id": jd_id, "display_id": display_id}


def requirement_statuses(db: Session, jd_id: str, candidate_ids: List[str]) -> dict:
    if not candidate_ids:
        return {}
    rows = db.query(RequirementCandidateStatus).filter(
        RequirementCandidateStatus.position_id == jd_id,
        RequirementCandidateStatus.candidate_id.in_(candidate_ids),
    ).all()
    return {r.candidate_id: r.status for r in rows}


def _latest_email_statuses(db: Session, jd_id: str, candidate_ids: List[str]) -> dict:
    if not candidate_ids:
        return {}
    rows = (
        db.query(EmailRecord.candidate_id, EmailRecord.status, EmailRecord.created_at)
        .filter(EmailRecord.position_id == jd_id, EmailRecord.candidate_id.in_(candidate_ids))
        .order_by(EmailRecord.created_at.asc())
        .all()
    )
    return {cid: {"status": status, "at": at.isoformat() if at else None} for cid, status, at in rows}


def _with_requirement_state(db: Session, jd_id: str, res: dict) -> dict:
    # Statuses and email activity are read live rather than cached, so the cached
    # (expensive) scoring result can never show a stale review status.
    ids = [m["candidate"]["id"] for m in res["matches"]]
    statuses = requirement_statuses(db, jd_id, ids)
    emails = _latest_email_statuses(db, jd_id, ids)
    matches = [
        {
            **m,
            "requirement_status": statuses.get(m["candidate"]["id"], DEFAULT_REQUIREMENT_STATUS),
            "last_email": emails.get(m["candidate"]["id"]),
        }
        for m in res["matches"]
    ]
    return {**res, "matches": matches}


def meets_match_threshold(score, threshold: float) -> bool:
    """match_score is on the 0-100 scale (see scoring.calculate_hybrid_score); a missing score never qualifies."""
    if not isinstance(score, (int, float)) or isinstance(score, bool) or math.isnan(score):
        return False
    return score >= threshold


def _unindexed_candidate_count(db: Session) -> int:
    # JD matching only scores candidates returned by Qdrant/OpenSearch retrieval, so a
    # resume that never reached the indexes (e.g. an interrupted upload batch) can never
    # appear under a requirement until it is reindexed.
    return db.query(Candidate.id).filter(Candidate.qdrant_point_id.is_(None)).count()


# Bump when extract_jd_filters changes, so values cached on positions are re-derived.
JD_FILTER_EXTRACTOR_VERSION = 2


def get_jd_search_filters(jd_id: str, db: Session) -> dict:
    """Location / role / work mode read from the JD, for pre-filling the search filters. Extracted
    once per (jd_version, title) and stored on the position, so re-selecting a JD costs nothing."""
    pos = get_jd(jd_id, db)
    stored = pos.search_filters or {}
    if stored.get("jd_version") != pos.jd_version or stored.get("title") != pos.title or stored.get("extractor") != JD_FILTER_EXTRACTOR_VERSION:
        stored = {**extract_jd_filters(pos.title, pos.jd_text), "jd_version": pos.jd_version, "title": pos.title, "extractor": JD_FILTER_EXTRACTOR_VERSION}
        pos.search_filters = stored
        db.commit()
    # The demand's own places win; the JD text's single place is the fallback.
    locations = pos.locations or [p for p in [stored.get("location")] if p]
    return {"position_id": pos.id, "jd_version": pos.jd_version, "location": stored.get("location"), "locations": locations, "role": stored.get("role"),
            "work_mode": stored.get("work_mode"), "sources": stored.get("sources") or {}}


def get_jd_matches(id: str, top_n: int, db: Session) -> dict:
    pos = get_jd(id, db)
    cache_key = f"requirements:matches:{id}:v{pos.jd_version}:{get_index_epoch()}:{top_n}"
    cached = get_cache(cache_key)
    if cached is not None:
        return _with_requirement_state(db, id, cached)

    matches_data = []
    total_matches = 0
    retrieval = None

    try:
        from backend.services.retrieval.search import execute_candidate_search
        search_res = execute_candidate_search(db, query_text="", position_id=id, top_n=top_n)
        matches_data = search_res.get("results", [])
        total_matches = search_res.get("total_matches", len(matches_data))
        retrieval = search_res.get("retrieval")
    except Exception as exc:
        logger.warning(f"[matches] Fallback to existing CandidateMatch rows: {exc}")
        db_matches = (
            db.query(CandidateMatch, Candidate)
            .join(Candidate, CandidateMatch.candidate_id == Candidate.id)
            .filter(CandidateMatch.position_id == id)
            .order_by(CandidateMatch.match_score.desc())
            .limit(top_n)
            .all()
        )
        matches_data = [
            {
                "candidate": {
                    "id": c.id,
                    "display_id": c.display_id,
                    "candidate_name": c.candidate_name,
                    "email": c.email,
                    "phone": c.phone,
                    "extracted_skills": c.extracted_skills or [],
                    "years_experience": c.years_experience,
                    "education": c.education,
                    "status": c.status,
                    "original_filename": c.original_filename,
                    "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
                    "resume_file_url": c.resume_file_url,
                },
                "match_score": m.match_score,
                "score_breakdown": m.score_breakdown or {},
                "llm_summary": m.llm_summary or "",
                "cited_quote": m.cited_quote or "",
                "cited_section": m.cited_section or "",
            }
            for m, c in db_matches
        ]
        total_matches = len(matches_data)

    # Requirements only show qualifying candidates; lower scores stay in the DB and in Search.
    threshold = settings.REQUIREMENT_MATCH_THRESHOLD
    qualified = [m for m in matches_data if meets_match_threshold(m.get("match_score"), threshold)]
    res = {
        "position_id": pos.id,
        "display_id": pos.display_id,
        "position_title": pos.title,
        "position_version": pos.jd_version,
        "min_match_score": threshold,
        "total_scored": total_matches,
        "total_matches": len(qualified),
        "matches": qualified,
        "retrieval": retrieval,
        "unindexed_candidates": _unindexed_candidate_count(db),
    }
    # Only cache long when every retrieval source answered; a degraded run (e.g. OpenSearch down) must not
    # pin lower scores for a day once the service recovers.
    healthy = bool(retrieval and retrieval.get("vector") and retrieval.get("lexical"))
    set_cache(cache_key, res, ttl_seconds=settings.CACHE_TTL_MATCHES if healthy else settings.CACHE_TTL_QUERY)
    return _with_requirement_state(db, id, res)


def set_requirement_candidate_status(jd_id: str, candidate_id: str, status: str, db: Session, user: User) -> dict:
    if status not in REQUIREMENT_STATUSES:
        raise HTTPException(400, f"Invalid status. Use one of: {', '.join(REQUIREMENT_STATUSES)}.")
    get_jd(jd_id, db)
    if not db.query(Candidate.id).filter(Candidate.id == candidate_id).first():
        raise HTTPException(404, "Candidate not found.")
    row = db.query(RequirementCandidateStatus).filter(
        RequirementCandidateStatus.position_id == jd_id,
        RequirementCandidateStatus.candidate_id == candidate_id,
    ).first()
    if row is None:
        row = RequirementCandidateStatus(position_id=jd_id, candidate_id=candidate_id)
        db.add(row)
    row.status = status
    row.updated_by = user.id
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"position_id": jd_id, "candidate_id": candidate_id, "status": row.status,
            "updated_by": row.updated_by, "updated_at": row.updated_at.isoformat()}


def summarize_jd_endpoint(jd_id: str, db: Session):
    pos = get_jd(jd_id, db)
    pos.jd_summary = summarize_jd(pos.title, pos.jd_text)
    db.commit()
    db.refresh(pos)
    invalidate_requirements_cache(pos.id)
    return {"id": pos.id, "display_id": pos.display_id, "title": pos.title, "jd_version": pos.jd_version, "jd_summary": pos.jd_summary}


async def _handle_jd_file_upload(file: UploadFile):
    filename = file.filename or "job_description.txt"
    if not is_supported_jd_file(filename):
        raise HTTPException(
            400,
            f"Unsupported file format '{os.path.splitext(filename)[1]}'. "
            "Supported formats: PDF (.pdf), Word Documents (.docx, .doc, .rtf, .odt, .txt, .md), "
            "and Images (.jpg, .jpeg, .png, .webp, .bmp, .tiff)."
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded JD file is empty.")

    # Save to dedicated JD storage folder
    file_url, _ = save_upload_file(filename, data, category="job_descriptions")

    # Extract text using comprehensive parser (PDF / Docx / RapidOCR for images)
    try:
        extracted_text = extract_text_from_file(filename, data)
    except Exception as exc:
        raise HTTPException(500, f"Error processing file for text extraction: {exc}")

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(400, "No readable text found in the uploaded JD file.")

    raw_title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").replace("-", " ").strip()
    clean_title = raw_title or "Uploaded Job Description"

    return clean_title, extracted_text.strip(), file_url, filename


# ============================================================
# API Endpoints
# ============================================================

@router.get("/api/job-descriptions", response_model=List[PositionResponse])
def get_job_descriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list_jds(db)


@router.post("/api/job-descriptions", response_model=PositionResponse)
def post_job_description(req: PositionCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return create_jd(req, db, user)


@router.post("/api/job-descriptions/extract-text", response_model=JDExtractResponse)
async def extract_job_description_text(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload a JD file (PDF, Word Document, or Image), save in dedicated folder, and return
    extracted text without immediately creating the position, allowing user review/edit in UI.
    """
    clean_title, extracted_text, file_url, filename = await _handle_jd_file_upload(file)
    result = classify_jd_detailed(clean_title, extracted_text)
    return JDExtractResponse(
        title=clean_title,
        jd_text=extracted_text,
        original_filename=filename,
        file_url=file_url,
        category=result.category,
        classification_note=result.note,
        **_detect_details(clean_title, extracted_text),
    )


@router.post("/api/job-descriptions/extract-details", response_model=JDDetectedDetails)
def extract_job_description_details(req: JDDetailsRequest, user: User = Depends(get_current_user)):
    """Read title, location and experience from pasted JD text, for the form to prefill and the user to review."""
    if not req.jd_text.strip():
        return JDDetectedDetails()
    return JDDetectedDetails(**_detect_details(req.title.strip(), req.jd_text))


@router.get("/api/job-descriptions/{id}", response_model=PositionResponse)
def get_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pos = get_jd(id, db)
    return _with_creator(pos, _creator_name(pos, db), db)


@router.get("/api/job-descriptions/{id}/search-filters")
def get_job_description_search_filters(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd_search_filters(id, db)


@router.get("/api/job-descriptions/{id}/file")
def download_job_description_file(id: str, download: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pos = get_jd(id, db)
    path = resolve_stored_file(pos.file_url)
    if not path:
        raise HTTPException(404, "Requirement file not available.")
    return FileResponse(
        path,
        filename=pos.original_filename or path.name,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.put("/api/job-descriptions/{id}", response_model=PositionResponse)
def put_job_description(id: str, req: PositionUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return update_jd(id, req, db, user)


@router.put("/api/job-descriptions/{id}/demand", response_model=PositionResponse)
def put_job_description_demand(id: str, req: PositionDemandRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_jd_demand(id, req.demand_id, db, user)


@router.put("/api/job-descriptions/{id}/status", response_model=PositionResponse)
def put_job_description_status(id: str, req: JDStatusRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_jd_status(id, req.status, db, user, req.cancellation_reason, req.candidate_ids)


@router.get("/api/requirement-history")
def get_requirement_history(action: Optional[str] = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every demand/JD creation, update, status change and deletion, newest first."""
    if action is not None and action not in HISTORY_ACTIONS:
        raise HTTPException(400, f"Invalid action. Use one of: {', '.join(HISTORY_ACTIONS)}.")
    limit = max(1, min(limit, 200))
    q = db.query(RequirementHistory)
    if action:
        q = q.filter(RequirementHistory.action == action)
    total = q.count()
    rows = q.order_by(RequirementHistory.created_at.desc(), RequirementHistory.id.desc()).offset(max(0, offset)).limit(limit).all()
    return {"total": total, "limit": limit, "offset": max(0, offset), "items": [history.serialize(r) for r in rows]}


@router.post("/api/job-descriptions/{id}/summarize")
def post_summarize_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)


@router.delete("/api/job-descriptions/{id}")
def delete_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return delete_jd(id, db, user)


@router.get("/api/job-descriptions/{id}/matches")
def get_job_description_matches(id: str, top_n: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd_matches(id, top_n, db)


@router.put("/api/job-descriptions/{id}/candidates/{candidate_id}/status")
def put_requirement_candidate_status(id: str, candidate_id: str, req: RequirementStatusRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_requirement_candidate_status(id, candidate_id, req.status, db, user)
