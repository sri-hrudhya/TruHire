from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.config import settings
from backend.models import (
    CANDIDATE_STATUSES, CLIENT_NAMES, DEFAULT_JD_STATUS, RESUME_LINKED_JD_STATUSES, DEFAULT_REQUIREMENT_STATUS, JD_STATUSES, NOTICE_PERIOD_UNITS, EMAIL_STATUS_FAILED, EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED,
    REQUIREMENT_STATUSES, ROLES, User,
)
from backend.routers.email import EMAIL_STATUS_PENDING

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("")
def get_meta(user: User = Depends(get_current_user)):
    """Enums and limits the UI needs, read from the same constants the backend enforces."""
    return {
        "roles": list(ROLES),
        "jd_statuses": list(JD_STATUSES),
        "default_jd_status": DEFAULT_JD_STATUS,
        "resume_linked_jd_statuses": list(RESUME_LINKED_JD_STATUSES),
        "client_names": list(CLIENT_NAMES),
        "notice_period_units": list(NOTICE_PERIOD_UNITS),
        "requirement_statuses": list(REQUIREMENT_STATUSES),
        "default_requirement_status": DEFAULT_REQUIREMENT_STATUS,
        "candidate_statuses": list(CANDIDATE_STATUSES),
        "email_statuses": [EMAIL_STATUS_PENDING, EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED, EMAIL_STATUS_FAILED],
        "page_sizes": {"history": settings.HISTORY_PAGE_SIZE, "audit": settings.AUDIT_PAGE_SIZE},
        "search": {"default_top_n": settings.SEARCH_DEFAULT_TOP_N, "max_top_n": settings.SEARCH_MAX_TOP_N},
        "comment_max_chars": settings.COMMENT_MAX_CHARS,
        "accepted_jd_file_types": settings.jd_accepted_extensions,
    }
