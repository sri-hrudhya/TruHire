"""Requirement Tracker: one row per candidate a recruiter has set a status on for a requirement."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.services.candidates.tracker_fields import resume_fields
from backend.models import Candidate, Position, RequirementCandidateStatus, User

router = APIRouter(prefix="/api/tracker", tags=["tracker"])

# (key, label) in table order. Read-only: values come from the candidate record and what the resume states.
COLUMNS = (
    ("primary_skill", "Primary Skill"), ("recruiter", "Recruiter"), ("source_name", "Source Name"),
    ("source_date", "Source Date"), ("interview_status", "Internal Interview Status"),
    ("candidate_name", "Candidate Name"), ("contact_no", "Contact No"), ("email", "Email ID"),
    ("total_experience", "Total Experience"), ("relevant_experience", "Relevant Experience"),
    ("payroll_company", "Payroll Company"), ("serving_notice", "Serving Notice"), ("notice_period", "Notice Period"),
    ("lwd", "LWD (Last Working Date)"), ("expected_joining", "Expected Joining Date"),
    ("current_ctc", "Current CTC"), ("expected_ctc", "Expected CTC"), ("current_location", "Current Location"),
    ("preferred_location", "Preferred Location"), ("offer_in_hand", "Offer in Hand"),
    ("reason_for_change", "Reason for Change"), ("domains", "Domains"), ("frameworks", "Frameworks"),
)
MAX_ROWS = 1000


def _auto(cand: Candidate, status: str, recruiter: Optional[str]) -> dict:
    notice = f"{cand.notice_period_value:g} {cand.notice_period_unit}" if cand.notice_period_value is not None and cand.notice_period_unit else None
    skills = cand.extracted_skills or []
    values = {
        "primary_skill": skills[0] if skills else None, "recruiter": recruiter,
        "source_date": cand.uploaded_at.isoformat() if cand.uploaded_at else None, "interview_status": status,
        "candidate_name": cand.candidate_name, "contact_no": cand.phone, "email": cand.email,
        "total_experience": f"{cand.years_experience:g} yrs" if cand.years_experience is not None else None,
        "payroll_company": cand.current_company, "notice_period": notice, "current_location": cand.location,
    }
    return {**resume_fields(cand.resume_text, skills), **{k: v for k, v in values.items() if v not in (None, "")}}


@router.get("")
def tracker_rows(position_id: Optional[str] = None, client: Optional[str] = None,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = (db.query(RequirementCandidateStatus, Candidate, Position, User.name)
             .join(Candidate, Candidate.id == RequirementCandidateStatus.candidate_id)
             .join(Position, Position.id == RequirementCandidateStatus.position_id)
             .outerjoin(User, User.id == RequirementCandidateStatus.updated_by))
    if position_id:
        query = query.filter(RequirementCandidateStatus.position_id == position_id)
    if client and client.strip():
        query = query.filter(func.lower(func.trim(Position.client_name)) == client.strip().lower())
    rows = query.order_by(Position.client_name, Position.display_id, RequirementCandidateStatus.updated_at.desc()).limit(MAX_ROWS).all()
    return {"columns": [{"key": k, "label": label} for k, label in COLUMNS],
            "rows": [{"position_id": pos.id, "candidate_id": cand.id, "demand_id": pos.display_id,
                      "demand_title": pos.title, "client_name": pos.client_name,
                      "values": _auto(cand, status.status, recruiter)}
                     for status, cand, pos, recruiter in rows]}
