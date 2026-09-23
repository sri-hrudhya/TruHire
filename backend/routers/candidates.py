from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Candidate, CandidateMatch, Position, User
from backend.auth import get_current_user

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


class CandidateStatusUpdateRequest(BaseModel):
    status: str  # New, Shortlisted, Interviewed, Rejected


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    position_id: Optional[str] = None
    candidate_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    extracted_skills: List[str] = []
    years_experience: float
    education: Optional[str] = None
    status: str
    status_updated_by: Optional[str] = None
    status_updated_at: Optional[datetime] = None
    uploaded_at: datetime
    original_filename: str
    resume_file_url: Optional[str] = None


@router.get("", response_model=dict)
def list_candidates(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Paginated list of candidates from the shared pool.
    Always bounded by limit (max 100).
    """
    bounded_limit = max(1, min(limit, 100))
    query = db.query(Candidate).order_by(Candidate.uploaded_at.desc())
    total = query.count()
    items = query.offset(offset).limit(bounded_limit).all()

    return {
        "total": total,
        "limit": bounded_limit,
        "offset": offset,
        "candidates": items
    }


@router.get("/{id}")
def get_candidate(
    id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get single candidate profile."""
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return cand


@router.patch("/{id}/status")
def update_candidate_status(
    id: str,
    req: CandidateStatusUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Update candidate recruitment status (New -> Shortlisted -> Interviewed -> Rejected)."""
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    valid_statuses = ["New", "Shortlisted", "Interviewed", "Rejected"]
    if req.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Must be one of: {', '.join(valid_statuses)}"
        )

    cand.status = req.status
    cand.status_updated_by = user.id
    cand.status_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cand)

    return {
        "id": cand.id,
        "status": cand.status,
        "status_updated_by": cand.status_updated_by,
        "status_updated_at": cand.status_updated_at
    }


@router.get("/{id}/matches")
def get_candidate_matches(
    id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Cross-JD match matrix: returns all match evaluations for this candidate across all JDs.
    """
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

    results = []
    for match, position in matches:
        results.append({
            "match_id": match.id,
            "position_id": position.id,
            "position_title": position.title,
            "jd_version": match.jd_version,
            "current_jd_version": position.jd_version,
            "is_version_current": match.jd_version == position.jd_version,
            "match_score": match.match_score,
            "score_breakdown": match.score_breakdown,
            "llm_summary": match.llm_summary,
            "cited_quote": match.cited_quote,
            "cited_section": match.cited_section,
            "updated_at": match.updated_at
        })

    return {
        "candidate_id": cand.id,
        "candidate_name": cand.candidate_name,
        "total_matched_positions": len(results),
        "matches": results
    }
