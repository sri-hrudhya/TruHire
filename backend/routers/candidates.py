from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Candidate, CandidateMatch, Position, RequirementCandidateStatus, User
from backend.auth import get_current_user
from backend.services.retrieval.opensearch import delete_candidate as delete_lexical
from backend.services.retrieval.qdrant import delete_candidate as delete_vector
from backend.services.common.cache import get_cache, set_cache, delete_cache, clear_cache
from backend.services.ingestion.storage import delete_file_by_url_or_path, resolve_stored_file
from backend.config import settings

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

class CandidateStatusUpdateRequest(BaseModel): status: str
class CandidateDeleteRequest(BaseModel): ids: List[str]

def invalidate_candidate_cache(candidate_id: Optional[str] = None):
    clear_cache("candidates:list:")
    clear_cache("requirements:matches:")
    clear_cache("search:")
    if candidate_id:
        delete_cache(f"candidate:detail:{candidate_id}")
        delete_cache(f"candidate:matches:{candidate_id}")


def _serialize_candidate(c: Candidate) -> Dict[str, Any]:
    return {
        "id": c.id,
        "display_id": c.display_id,
        "position_id": c.position_id,
        "candidate_name": c.candidate_name,
        "email": c.email,
        "phone": c.phone,
        "extracted_skills": c.extracted_skills or [],
        "years_experience": c.years_experience,
        "education": c.education,
        "resume_text": c.resume_text,
        "status": c.status,
        "status_updated_by": c.status_updated_by,
        "status_updated_at": c.status_updated_at.isoformat() if c.status_updated_at else None,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        "original_filename": c.original_filename,
        "resume_file_url": c.resume_file_url,
    }


@router.get("", response_model=dict)
def list_candidates(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bounded = max(1, min(limit, 100))
    cache_key = f"candidates:list:{bounded}:{offset}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    q = db.query(Candidate).order_by(Candidate.uploaded_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(bounded).all()
    data = {
        "total": total,
        "limit": bounded,
        "offset": offset,
        "candidates": [_serialize_candidate(c) for c in rows]
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
    if req.status not in ["New", "Shortlisted", "Interviewed", "Rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status.")
    cand.status = req.status
    cand.status_updated_by = user.id
    cand.status_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cand)
    invalidate_candidate_cache(id)
    return {"id": cand.id, "display_id": cand.display_id, "status": cand.status, "status_updated_by": cand.status_updated_by, "status_updated_at": cand.status_updated_at}


def _remove_candidate(cand: Candidate, db: Session):
    delete_vector(cand.id)
    delete_lexical(cand.id)
    if resolve_stored_file(cand.resume_file_url):
        delete_file_by_url_or_path(cand.resume_file_url)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.candidate_id == cand.id).delete(synchronize_session=False)
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
            }
            for m, p in matches
        ],
    }
    set_cache(cache_key, result, ttl_seconds=settings.CACHE_TTL_QUERY)
    return result

