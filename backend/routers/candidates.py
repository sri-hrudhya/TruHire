from datetime import datetime
from base64 import urlsafe_b64decode, urlsafe_b64encode
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import CANDIDATE_STATUSES, DEFAULT_REQUIREMENT_STATUS, NOTICE_PERIOD_UNITS, Candidate, CandidateActivity, CandidateAssignment, CandidateComment, CandidateMatch, Position, RequirementCandidateStatus, User
from backend.auth import get_current_user
from backend.services.common.payloads import candidate_payload
from backend.services.retrieval.opensearch import delete_candidate as delete_lexical
from backend.services.retrieval.qdrant import delete_candidate as delete_vector
from backend.services.common.cache import get_cache, set_cache, delete_cache, clear_cache
from backend.services.ingestion.storage import delete_file_by_url_or_path, resolve_stored_file
from backend.config import settings
from backend.services.candidates.directory import filter_directory

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
logger = logging.getLogger(__name__)

class CandidateStatusUpdateRequest(BaseModel): status: str
class CandidateAvailabilityUpdateRequest(BaseModel): status: str
class CandidateDeleteRequest(BaseModel): ids: List[str]

MAX_NOTICE_DAYS = 365 * 2
_UNIT_DAYS = {"Days": 1, "Weeks": 7, "Months": 30}


class NoticePeriodRequest(BaseModel):
    """Both fields null clears the notice period; otherwise a non-negative number and a known unit."""
    value: Optional[float] = Field(default=None, ge=0)
    unit: Optional[str] = None

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, unit):
        if unit is not None and unit not in NOTICE_PERIOD_UNITS:
            raise ValueError(f"must be one of: {', '.join(NOTICE_PERIOD_UNITS)}")
        return unit

    def check(self) -> None:
        if (self.value is None) != (self.unit is None):
            raise HTTPException(status_code=422, detail="Notice period needs both a number and a unit (Days, Weeks or Months).")
        if self.value is not None and self.value * _UNIT_DAYS[self.unit] > MAX_NOTICE_DAYS:
            raise HTTPException(status_code=422, detail="Notice period cannot exceed 2 years.")

def invalidate_candidate_cache(candidate_id: Optional[str] = None):
    clear_cache("candidates:list:")
    clear_cache("requirements:matches:")
    clear_cache("search:")
    if candidate_id:
        delete_cache(f"candidate:detail:{candidate_id}")
        delete_cache(f"candidate:matches:{candidate_id}")


def _serialize_candidate(c: Candidate) -> Dict[str, Any]:
    return {
        **candidate_payload(c),
        "position_id": c.position_id,
        "resume_text": c.resume_text,
        "notice_period_value": c.notice_period_value,
        "notice_period_unit": c.notice_period_unit,
        "status_updated_by": c.status_updated_by,
        "status_updated_at": c.status_updated_at.isoformat() if c.status_updated_at else None,
        "availability_updated_by": c.availability_updated_by,
        "availability_updated_at": c.availability_updated_at.isoformat() if c.availability_updated_at else None,
    }


@router.get("", response_model=dict)
def list_candidates(limit: int = 20, offset: int = 0, q: Optional[str] = None, uploaded_by: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """uploaded_by omitted: every resume (search/review callers). Given: "me" or a user id narrows to that
    uploader and "all" lifts the filter, but only admins may look at anyone but themselves."""
    bounded = max(1, min(limit, 100))
    needle = (q or "").strip()[:100]
    uploader_id = None
    if uploaded_by:
        if user.role != "admin" or uploaded_by == "me":
            uploader_id = user.id
        elif uploaded_by != "all":
            uploader_id = uploaded_by
    cache_key = f"candidates:list:{bounded}:{offset}:{needle.lower()}:{uploader_id or '*'}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    query = db.query(Candidate)
    if uploader_id:
        query = query.filter(Candidate.uploaded_by == uploader_id)
    if needle:
        query = filter_directory(query, needle)
    else:
        query = query.order_by(Candidate.uploaded_at.desc())
    total = query.count()
    rows = query.offset(offset).limit(bounded).all()
    names = dict(db.query(User.id, User.name).filter(User.id.in_({c.uploaded_by for c in rows})).all()) if rows else {}
    data = {
        "total": total,
        "limit": bounded,
        "offset": offset,
        "candidates": [{**_serialize_candidate(c), "uploaded_by_name": names.get(c.uploaded_by)} for c in rows]
    }
    set_cache(cache_key, data, ttl_seconds=settings.CACHE_TTL_QUERY)
    return data


@router.get("/{id}")
def get_candidate(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cache_key = f"candidate:detail:{id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    data = _serialize_candidate(cand)
    set_cache(cache_key, data, ttl_seconds=settings.CACHE_TTL_QUERY)
    return data


@router.get("/{id}/resume")
def download_candidate_resume(id: str, download: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Stream the original resume file. Files are never served statically, so this is the only, authenticated, way in."""
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    path = resolve_stored_file(cand.resume_file_url)
    if not path:
        raise HTTPException(status_code=404, detail="Resume file not available.")
    return FileResponse(
        path,
        filename=cand.original_filename or path.name,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.patch("/{id}/status")
def update_candidate_status(id: str, req: CandidateStatusUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    if req.status not in CANDIDATE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status.")
    previous = cand.status
    cand.status = req.status
    cand.status_updated_by = user.id
    cand.status_updated_at = datetime.utcnow()
    if previous != req.status:
        db.add(CandidateActivity(candidate_id=id, event_type="candidate_status_changed", actor_id=user.id,
                                 actor_name=user.name, occurred_at=cand.status_updated_at,
                                 summary=f"Status changed from {previous or 'Unknown'} to {req.status}."))
    db.commit()
    db.refresh(cand)
    invalidate_candidate_cache(id)
    return {"id": cand.id, "display_id": cand.display_id, "status": cand.status, "status_updated_by": cand.status_updated_by, "status_updated_at": cand.status_updated_at}


@router.patch("/{id}/availability")
def update_candidate_availability(id: str, req: CandidateAvailabilityUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if req.status not in ("Active", "Not Active"):
        raise HTTPException(status_code=400, detail="Availability must be Active or Not Active.")
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    previous = cand.availability_status or "Active"
    cand.availability_status = req.status
    cand.availability_updated_by = user.id
    cand.availability_updated_at = datetime.utcnow()
    if previous != req.status:
        db.add(CandidateActivity(candidate_id=id, event_type="availability_status_changed", actor_id=user.id,
                                 actor_name=user.name, occurred_at=cand.availability_updated_at,
                                 summary=f"Availability changed from {previous} to {req.status}."))
    db.commit()
    db.refresh(cand)
    invalidate_candidate_cache(id)
    return {"id": cand.id, "display_id": cand.display_id, "availability_status": cand.availability_status,
            "availability_updated_by": cand.availability_updated_by,
            "availability_updated_at": cand.availability_updated_at.isoformat() if cand.availability_updated_at else None}


@router.get("/{id}/history")
def candidate_history(id: str, limit: int = 50, cursor: Optional[str] = None,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Candidate.id).filter(Candidate.id == id).first():
        raise HTTPException(404, "Candidate not found.")
    limit = max(1, min(limit, 100))
    query = db.query(CandidateActivity).filter(CandidateActivity.candidate_id == id)
    if cursor:
        try:
            raw = urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
            timestamp, event_id = raw.split("|", 1)
            before = datetime.fromisoformat(timestamp)
        except Exception:
            raise HTTPException(422, "Invalid history cursor.") from None
        query = query.filter(or_(CandidateActivity.occurred_at < before,
                                 and_(CandidateActivity.occurred_at == before, CandidateActivity.id < event_id)))
    rows = query.order_by(CandidateActivity.occurred_at.desc(), CandidateActivity.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = urlsafe_b64encode(f"{last.occurred_at.isoformat()}|{last.id}".encode()).decode("ascii")
    candidate = db.get(Candidate, id)
    requirement_rows = (db.query(RequirementCandidateStatus, Position, User)
                        .join(Position, Position.id == RequirementCandidateStatus.position_id)
                        .outerjoin(User, User.id == RequirementCandidateStatus.updated_by)
                        .filter(RequirementCandidateStatus.candidate_id == id)
                        .order_by(RequirementCandidateStatus.updated_at.desc()).all())
    requirements = [{"id": position.id, "display_id": position.display_id, "title": position.title,
                     "client_name": position.client_name, "demand_owner": position.demand_owner, "status": status.status,
                     "last_modified": status.updated_at.isoformat() if status.updated_at else None,
                     "modified_by": actor.name if actor else None}
                    for status, position, actor in requirement_rows]
    known_positions = {item["id"] for item in requirements}
    match_rows = (db.query(CandidateMatch, Position)
                  .join(Position, Position.id == CandidateMatch.position_id)
                  .filter(CandidateMatch.candidate_id == id)
                  .order_by(CandidateMatch.updated_at.desc()).all())
    requirements.extend({"id": position.id, "display_id": position.display_id, "title": position.title,
                         "client_name": position.client_name, "demand_owner": position.demand_owner, "status": DEFAULT_REQUIREMENT_STATUS,
                         "last_modified": match.updated_at.isoformat() if match.updated_at else None,
                         "modified_by": None}
                        for match, position in match_rows if position.id not in known_positions)
    known_positions.update(item["id"] for item in requirements)
    assignment_rows = (db.query(CandidateAssignment, Position, User)
                       .join(Position, Position.id == CandidateAssignment.position_id)
                       .outerjoin(User, User.id == CandidateAssignment.assigned_by)
                       .filter(CandidateAssignment.candidate_id == id)
                       .order_by(CandidateAssignment.created_at.desc()).all())
    requirements.extend({"id": position.id, "display_id": position.display_id, "title": position.title,
                         "client_name": position.client_name, "demand_owner": position.demand_owner, "status": DEFAULT_REQUIREMENT_STATUS,
                         "last_modified": assignment.created_at.isoformat() if assignment.created_at else None,
                         "modified_by": actor.name if actor else None}
                        for assignment, position, actor in assignment_rows if position.id not in known_positions)
    requirements.sort(key=lambda item: item["last_modified"] or "", reverse=True)
    return {"current_status": {"status": candidate.status,
                                "last_modified": candidate.status_updated_at.isoformat() if candidate.status_updated_at else None,
                                "modified_by": db.query(User.name).filter(User.id == candidate.status_updated_by).scalar() if candidate.status_updated_by else None},
            "requirements": requirements,
            "items": [{"id": row.id, "event_type": row.event_type,
                       "timestamp": row.occurred_at.isoformat(), "actor": row.actor_name,
                       "summary": row.summary, "client_name": row.client_name,
                       "position_id": row.position_id, "position_title": row.position_title}
                      for row in rows], "next_cursor": next_cursor, "has_more": has_more}


@router.patch("/{id}/notice-period")
def update_notice_period(id: str, req: NoticePeriodRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    req.check()
    cand.notice_period_value = req.value
    cand.notice_period_unit = req.unit
    db.commit()
    invalidate_candidate_cache(id)
    return {"id": cand.id, "notice_period_value": cand.notice_period_value, "notice_period_unit": cand.notice_period_unit}


def _remove_candidate(cand: Candidate, db: Session):
    # SQL is the source of truth. Index deletion is best effort: stale index hits are
    # discarded when candidate IDs are joined back to PostgreSQL during retrieval.
    for index_name, delete_from_index in (("Qdrant", delete_vector), ("OpenSearch", delete_lexical)):
        try:
            delete_from_index(cand.id)
        except Exception:
            logger.exception("Could not remove candidate %s from %s; database deletion will continue", cand.id, index_name)
    if resolve_stored_file(cand.resume_file_url):
        delete_file_by_url_or_path(cand.resume_file_url)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.candidate_id == cand.id).delete(synchronize_session=False)
    db.query(CandidateAssignment).filter(CandidateAssignment.candidate_id == cand.id).delete(synchronize_session=False)
    db.query(CandidateComment).filter(CandidateComment.candidate_id == cand.id).delete(synchronize_session=False)
    db.delete(cand)


@router.delete("/{id}")
def delete_candidate(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    _remove_candidate(cand, db)
    db.commit()
    invalidate_candidate_cache(id)
    return {"deleted": 1, "ids": [id]}


@router.post("/bulk-delete")
def bulk_delete_candidates(req: CandidateDeleteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = list(dict.fromkeys(req.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="ids cannot be empty.")
    candidates = db.query(Candidate).filter(Candidate.id.in_(ids)).all()
    found = {c.id for c in candidates}
    for c in candidates:
        _remove_candidate(c, db)
    db.commit()
    for cid in ids:
        delete_cache(f"candidate:detail:{cid}")
        delete_cache(f"candidate:matches:{cid}")
    invalidate_candidate_cache()
    return {"deleted": len(candidates), "ids": list(found), "not_found": [i for i in ids if i not in found]}


@router.get("/{id}/matches")
def get_candidate_matches(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cache_key = f"candidate:matches:{id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    matches = (
        db.query(CandidateMatch, Position)
        .join(Position, CandidateMatch.position_id == Position.id)
        .filter(CandidateMatch.candidate_id == id)
        .order_by(CandidateMatch.match_score.desc())
        .all()
    )
    result = {
        "candidate_id": id,
        "display_id": cand.display_id,
        "candidate_name": cand.candidate_name,
        "total_matched_positions": len(matches),
        "matches": [
            {
                "match_id": m.id,
                "position_id": p.id,
                "position_display_id": p.display_id,
                "position_title": p.title,
                "jd_version": m.jd_version,
                "current_jd_version": p.jd_version,
                "is_version_current": m.jd_version == p.jd_version,
                "match_score": m.match_score,
                "score_breakdown": m.score_breakdown,
                "llm_summary": m.llm_summary,
                "cited_quote": m.cited_quote,
                "cited_section": m.cited_section,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                "client_name": p.client_name,
                "requirement_status": (db.query(RequirementCandidateStatus.status).filter(
                    RequirementCandidateStatus.position_id == p.id,
                    RequirementCandidateStatus.candidate_id == id).scalar() or DEFAULT_REQUIREMENT_STATUS),
            }
            for m, p in matches
        ],
    }
    set_cache(cache_key, result, ttl_seconds=settings.CACHE_TTL_QUERY)
    return result

