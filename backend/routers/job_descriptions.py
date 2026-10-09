import math
import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    Position, User, Candidate, CandidateMatch, SearchState, Conversation, EmailRecord,
    RequirementCandidateStatus, REQUIREMENT_STATUSES, DEFAULT_REQUIREMENT_STATUS, get_next_position_display_id,
)
from backend.auth import get_current_user
from backend.config import settings
from backend.services.common.cache import get_cache, set_cache, delete_cache, clear_cache
from backend.services.ingestion.parsing import extract_text_from_file, is_supported_jd_file
from backend.services.ingestion.storage import resolve_stored_file, save_upload_file
from backend.services.llm.ai_service import summarize_jd

router = APIRouter(tags=["job-descriptions"])


class PositionCreateRequest(BaseModel):
    title: str
    jd_text: str
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


class PositionUpdateRequest(BaseModel):
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


class RequirementStatusRequest(BaseModel):
    status: str


class JDExtractResponse(BaseModel):
    title: str
    jd_text: str
    original_filename: str
    file_url: str


def invalidate_requirements_cache(jd_id: Optional[str] = None):
    delete_cache("requirements:list")
    clear_cache("truhire:site:jds:")
    clear_cache("search:")
    # Email history shows live requirement titles/deletion state.
    clear_cache("email:history:")
    if jd_id:
        delete_cache(f"requirements:detail:{jd_id}")
        clear_cache(f"requirements:matches:{jd_id}")


def _serialize_position(pos: Position) -> dict:
    return {
        "id": pos.id,
        "display_id": pos.display_id,
        "title": pos.title,
        "jd_text": pos.jd_text,
        "jd_summary": pos.jd_summary,
        "jd_version": pos.jd_version,
        "created_by": pos.created_by,
        "created_at": pos.created_at.isoformat() if pos.created_at else None,
        "file_url": pos.file_url,
        "original_filename": pos.original_filename,
    }


def list_jds(db: Session):
    cache_key = "requirements:list"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    positions = db.query(Position).order_by(Position.created_at.desc()).all()
    data = [_serialize_position(p) for p in positions]
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
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    invalidate_requirements_cache()
    return pos


def get_jd(jd_id: str, db: Session) -> Position:
    pos = db.query(Position).filter(Position.id == jd_id).first()
    if not pos:
        raise HTTPException(404, "Requirement not found.")
    return pos


def update_jd(jd_id: str, req: PositionUpdateRequest, db: Session) -> Position:
    pos = get_jd(jd_id, db)
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
    if changed:
        db.commit()
        db.refresh(pos)
        invalidate_requirements_cache(pos.id)
    return pos


def delete_jd(jd_id: str, db: Session) -> dict:
    pos = get_jd(jd_id, db)
    display_id = pos.display_id
    # Delete associated CandidateMatch rows for this requirement
    db.query(CandidateMatch).filter(CandidateMatch.position_id == jd_id).delete(synchronize_session=False)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.position_id == jd_id).delete(synchronize_session=False)
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


def get_jd_matches(id: str, top_n: int, db: Session) -> dict:
    pos = get_jd(id, db)
    cache_key = f"requirements:matches:{id}:{top_n}"
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
        print(f"[matches] Fallback to existing CandidateMatch rows: {exc}")
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
    set_cache(cache_key, res, ttl_seconds=settings.CACHE_TTL_QUERY)
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
    return JDExtractResponse(
        title=clean_title,
        jd_text=extracted_text,
        original_filename=filename,
        file_url=file_url,
    )


@router.get("/api/job-descriptions/{id}", response_model=PositionResponse)
def get_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd(id, db)


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
    return update_jd(id, req, db)


@router.post("/api/job-descriptions/{id}/summarize")
def post_summarize_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return summarize_jd_endpoint(id, db)


@router.delete("/api/job-descriptions/{id}")
def delete_job_description(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return delete_jd(id, db)


@router.get("/api/job-descriptions/{id}/matches")
def get_job_description_matches(id: str, top_n: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_jd_matches(id, top_n, db)


@router.put("/api/job-descriptions/{id}/candidates/{candidate_id}/status")
def put_requirement_candidate_status(id: str, candidate_id: str, req: RequirementStatusRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return set_requirement_candidate_status(id, candidate_id, req.status, db, user)
