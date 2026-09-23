from typing import Optional
from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Candidate, CandidateMatch, User
from backend.auth import get_current_user
from backend.services.export import export_candidates_to_csv, export_candidates_to_json

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/candidates")
def export_candidates(
    format: str = Query("csv", pattern="^(csv|json)$"),
    status: Optional[str] = None,
    position_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Export candidates/shortlist to CSV or JSON.
    """
    query = db.query(Candidate)
    if status:
        query = query.filter(Candidate.status == status)

    candidates = query.all()

    # Pre-fetch match scores if position_id specified
    match_map = {}
    if position_id:
        matches = db.query(CandidateMatch).filter(CandidateMatch.position_id == position_id).all()
        match_map = {m.candidate_id: m.match_score for m in matches}

    export_records = []
    for c in candidates:
        export_records.append({
            "id": c.id,
            "candidate_name": c.candidate_name,
            "email": c.email,
            "phone": c.phone,
            "years_experience": c.years_experience,
            "education": c.education,
            "status": c.status,
            "skills": c.extracted_skills or [],
            "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else "",
            "match_score": match_map.get(c.id, "")
        })

    if format == "json":
        json_content = export_candidates_to_json(export_records)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=truhire_candidates.json"}
        )
    else:
        csv_content = export_candidates_to_csv(export_records)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=truhire_candidates.csv"}
        )
