import re
from typing import Optional
from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Candidate, CandidateMatch, Position, User
from backend.auth import get_current_user
from backend.services.common.export import (
    export_candidates_to_csv,
    export_candidates_to_xlsx,
    export_candidates_to_json,
)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/candidates")
def export_candidates(
    format: str = Query("xlsx", pattern="^(csv|json|xlsx|excel)$"),
    status: Optional[str] = None,
    position_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Export candidate profiles and match scores to Excel (.xlsx), CSV, or JSON.
    """
    target_position = None
    if position_id:
        target_position = db.query(Position).filter(Position.id == position_id).first()

    query = db.query(Candidate)
    if status:
        query = query.filter(Candidate.status == status)

    candidates = query.all()

    # Pre-fetch match data if position_id specified
    match_map = {}
    if position_id:
        matches = db.query(CandidateMatch).filter(CandidateMatch.position_id == position_id).all()
        match_map = {m.candidate_id: m for m in matches}

    export_records = []
    for c in candidates:
        match = match_map.get(c.id)
        score_val = match.match_score if match else None
        score_display = f"{score_val:.1f}%" if score_val is not None else ""

        export_records.append({
            "candidate_name": c.candidate_name,
            "status": c.status,
            "match_score": score_display,
            "match_score_raw": score_val if score_val is not None else -1.0,
            "target_position": target_position.title if target_position else "",
            "ai_summary": (match.llm_summary or "") if match else "",
            "cited_quote": (match.cited_quote or "") if match else "",
            "cited_section": (match.cited_section or "") if match else "",
            "years_experience": c.years_experience if c.years_experience is not None else 0.0,
            "skills": c.extracted_skills or [],
            "education": c.education or "",
            "email": c.email or "",
            "phone": c.phone or "",
            "resume_filename": c.original_filename or "",
            "uploaded_at": c.uploaded_at.strftime("%Y-%m-%d %H:%M") if c.uploaded_at else "",
            "id": c.id,
        })

    # Sort: If position_id is given, sort by highest match score first; otherwise by uploaded_at
    if position_id:
        export_records.sort(key=lambda r: r.get("match_score_raw", -1.0), reverse=True)
    else:
        export_records.sort(key=lambda r: r.get("uploaded_at", ""), reverse=True)

    pos_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', target_position.title).strip('_') if target_position else ""
    base_filename = f"truhire_candidates_{pos_slug}" if pos_slug else "truhire_candidates"

    if format in ("xlsx", "excel"):
        xlsx_bytes = export_candidates_to_xlsx(export_records)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{base_filename}.xlsx"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    elif format == "json":
        json_content = export_candidates_to_json(export_records)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{base_filename}.json"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    else:
        csv_content = export_candidates_to_csv(export_records)
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base_filename}.csv"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
