from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Candidate, CandidateMatch, Position, User
from backend.auth import get_current_user
from backend.services.opensearch import delete_candidate as delete_lexical
from backend.services.qdrant import delete_candidate as delete_vector
from backend.services.cache import clear_cache
import os
from pathlib import Path
from backend.config import settings

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

class CandidateStatusUpdateRequest(BaseModel): status: str
class CandidateDeleteRequest(BaseModel): ids: List[str]
class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; position_id: Optional[str] = None; candidate_name: str; email: Optional[str] = None; phone: Optional[str] = None
    extracted_skills: List[str] = []; years_experience: float; education: Optional[str] = None; status: str
    status_updated_by: Optional[str] = None; status_updated_at: Optional[datetime] = None; uploaded_at: datetime; original_filename: str; resume_file_url: Optional[str] = None

@router.get("", response_model=dict)
def list_candidates(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bounded = max(1, min(limit, 100)); q = db.query(Candidate).order_by(Candidate.uploaded_at.desc()); total = q.count()
    return {"total": total, "limit": bounded, "offset": offset, "candidates": q.offset(offset).limit(bounded).all()}

@router.get("/{id}")
def get_candidate(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand: raise HTTPException(status_code=404, detail="Candidate not found.")
    return cand

@router.patch("/{id}/status")
def update_candidate_status(id: str, req: CandidateStatusUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand: raise HTTPException(status_code=404, detail="Candidate not found.")
    if req.status not in ["New", "Shortlisted", "Interviewed", "Rejected"]: raise HTTPException(status_code=400, detail="Invalid status.")
    cand.status = req.status; cand.status_updated_by = user.id; cand.status_updated_at = datetime.utcnow(); db.commit(); db.refresh(cand)
    return {"id": cand.id, "status": cand.status, "status_updated_by": cand.status_updated_by, "status_updated_at": cand.status_updated_at}


def _remove_candidate(cand: Candidate, db: Session):
    delete_vector(cand.id); delete_lexical(cand.id)
    if cand.resume_file_url:
        rel = cand.resume_file_url.removeprefix("/uploads/")
        try: Path(settings.STORAGE_DIR, rel).unlink(missing_ok=True)
        except Exception: pass
    db.delete(cand)

@router.delete("/{id}")
def delete_candidate(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand: raise HTTPException(status_code=404, detail="Candidate not found.")
    _remove_candidate(cand, db); db.commit(); clear_cache()
    return {"deleted": 1, "ids": [id]}

@router.post("/bulk-delete")
def bulk_delete_candidates(req: CandidateDeleteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = list(dict.fromkeys(req.ids))
    if not ids: raise HTTPException(status_code=400, detail="ids cannot be empty.")
    candidates = db.query(Candidate).filter(Candidate.id.in_(ids)).all()
    found = {c.id for c in candidates}
    for c in candidates: _remove_candidate(c, db)
    db.commit(); clear_cache()
    return {"deleted": len(candidates), "ids": list(found), "not_found": [i for i in ids if i not in found]}

@router.delete("")
def delete_candidates_query(ids: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alternative bulk delete: DELETE /api/candidates?ids=id1,id2,id3"""
    parsed = [x.strip() for x in ids.split(",") if x.strip()]
    return bulk_delete_candidates(CandidateDeleteRequest(ids=parsed), db, user)

@router.get("/{id}/matches")
def get_candidate_matches(id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cand = db.query(Candidate).filter(Candidate.id == id).first()
    if not cand: raise HTTPException(status_code=404, detail="Candidate not found.")
    matches = db.query(CandidateMatch, Position).join(Position, CandidateMatch.position_id == Position.id).filter(CandidateMatch.candidate_id == id).order_by(CandidateMatch.match_score.desc()).all()
    return {"candidate_id": id, "candidate_name": cand.candidate_name, "total_matched_positions": len(matches), "matches": [{"match_id": m.id, "position_id": p.id, "position_title": p.title, "jd_version": m.jd_version, "current_jd_version": p.jd_version, "is_version_current": m.jd_version == p.jd_version, "match_score": m.match_score, "score_breakdown": m.score_breakdown, "llm_summary": m.llm_summary, "cited_quote": m.cited_quote, "cited_section": m.cited_section, "updated_at": m.updated_at} for m,p in matches]}
