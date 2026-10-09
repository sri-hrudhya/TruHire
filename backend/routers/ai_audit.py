from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import AIAuditEvent, User

router = APIRouter(prefix="/api/ai-audit", tags=["ai-audit"])


def _serialize(e: AIAuditEvent) -> dict:
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "trace_id": e.trace_id,
        "user_id": e.user_id,
        "feature": e.feature,
        "provider": e.provider,
        "model": e.model,
        "status": e.status,
        "prompt_sha256": e.prompt_sha256,
        "prompt_preview": e.prompt_preview,
        "output_preview": e.output_preview,
        "prompt_tokens": e.prompt_tokens,
        "completion_tokens": e.completion_tokens,
        "latency_ms": e.latency_ms,
        "details": e.details or {},
        "error": e.error,
    }


@router.get("")
def list_ai_audit_events(
    feature: Optional[str] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # TODO(roles): restrict to admins once the user model has roles.
    q = db.query(AIAuditEvent)
    for column, value in ((AIAuditEvent.feature, feature), (AIAuditEvent.status, status), (AIAuditEvent.provider, provider),
                          (AIAuditEvent.user_id, user_id), (AIAuditEvent.trace_id, trace_id)):
        if value:
            q = q.filter(column == value)
    if date_from:
        q = q.filter(AIAuditEvent.created_at >= date_from)
    if date_to:
        q = q.filter(AIAuditEvent.created_at <= date_to)
    total = q.count()
    rows = q.order_by(AIAuditEvent.created_at.desc()).offset(max(0, offset)).limit(max(1, min(limit, 200))).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_serialize(e) for e in rows]}
