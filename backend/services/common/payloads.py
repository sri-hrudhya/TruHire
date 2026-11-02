"""API payload shapes shared by several routers and services."""
from __future__ import annotations

from typing import Any, Dict

from backend.models import Candidate


def candidate_payload(c: Candidate) -> Dict[str, Any]:
    """The candidate fields every list/search/match response carries."""
    return {
        "id": c.id, "display_id": c.display_id, "candidate_name": c.candidate_name, "email": c.email, "phone": c.phone,
        "extracted_skills": c.extracted_skills or [], "years_experience": c.years_experience,
        "education": c.education, "status": c.status, "original_filename": c.original_filename,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        "resume_file_url": c.resume_file_url,
        "location": c.location, "job_titles": c.job_titles or [],
    }
