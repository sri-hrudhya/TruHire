from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models import (
    Candidate, CandidateMatch, EmailRecord, Position, User,
    EMAIL_STATUS_FAILED, EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED,
)
from backend.routers.job_descriptions import get_jd, requirement_statuses
from backend.services.common.cache import clear_cache, get_cache, set_cache
from backend.services.common.email_delivery import deliver_email, delivery_mode, sender_address
from backend.services.llm.ai_service import EmailGenerationError, generate_candidate_email

router = APIRouter(prefix="/api/email", tags=["email"])

EMAIL_STATUS_PENDING = "pending"
SUCCESS_STATUSES = (EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED)
MAX_CANDIDATES_PER_REQUEST = 50


class EmailGenerateRequest(BaseModel):
    position_id: str
    candidate_ids: List[str] = Field(..., min_length=1, max_length=MAX_CANDIDATES_PER_REQUEST)


class EmailDraft(BaseModel):
    candidate_id: str
    subject: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1)
    idempotency_key: Optional[str] = Field(default=None, max_length=100)


class EmailSendRequest(BaseModel):
    position_id: str
    emails: List[EmailDraft] = Field(..., min_length=1, max_length=MAX_CANDIDATES_PER_REQUEST)
    allow_resend: bool = False


def invalidate_email_cache():
    clear_cache("email:")


def _serialize_record(r: EmailRecord) -> dict:
    return {
        "id": r.id,
        "position_id": r.position_id,
        "position_display_id": r.position_display_id,
        "position_title": r.position_title,
        "candidate_id": r.candidate_id,
        "candidate_display_id": r.candidate_display_id,
        "candidate_name": r.candidate_name,
        "recipient_email": r.recipient_email,
        "subject": r.subject,
        "body": r.body,
        "status": r.status,
        "delivery_mode": r.delivery_mode,
        "error": r.error,
        "attempts": r.attempts,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _shortlisted_candidates(db: Session, position_id: str, candidate_ids: List[str]):
    """Returns ({id: Candidate} for shortlisted ids, [rejection dicts] for the rest)."""
    ids = list(dict.fromkeys(candidate_ids))
    found = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(ids)).all()}
    statuses = requirement_statuses(db, position_id, ids)
    eligible, rejected = {}, []
    for cid in ids:
        cand = found.get(cid)
        if cand is None:
            rejected.append({"candidate_id": cid, "reason": "Candidate not found."})
        elif statuses.get(cid) != "Shortlisted":
            rejected.append({"candidate_id": cid, "candidate_name": cand.candidate_name, "reason": "Candidate is not Shortlisted for this requirement."})
        elif not (cand.email or "").strip():
            rejected.append({"candidate_id": cid, "candidate_name": cand.candidate_name, "reason": "Candidate has no email address."})
        else:
            eligible[cid] = cand
    return eligible, rejected


@router.get("/config")
def get_email_config(user: User = Depends(get_current_user)):
    return {
        "delivery_mode": delivery_mode(),
        "from_address": sender_address(),
        "company_name": settings.COMPANY_NAME,
    }


@router.post("/generate")
def generate_emails(req: EmailGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pos = get_jd(req.position_id, db)
    eligible, rejected = _shortlisted_candidates(db, pos.id, req.candidate_ids)
    breakdowns = {
        m.candidate_id: (m.score_breakdown or {})
        for m in db.query(CandidateMatch).filter(
            CandidateMatch.position_id == pos.id, CandidateMatch.candidate_id.in_(list(eligible))
        ).all()
    }

    drafts, errors = [], list(rejected)
    for cid, cand in eligible.items():
        try:
            generated = generate_candidate_email(
                jd_title=pos.title,
                jd_text=pos.jd_text,
                jd_summary=pos.jd_summary,
                candidate_name=cand.candidate_name,
                candidate_skills=cand.extracted_skills or [],
                years_experience=cand.years_experience or 0,
                education=cand.education,
                resume_text=cand.resume_text,
                matched_skills=breakdowns.get(cid, {}).get("matched_skills") or [],
                recruiter_name=user.name,
                company_name=settings.COMPANY_NAME,
                company_description=settings.COMPANY_DESCRIPTION,
            )
        except EmailGenerationError as exc:
            errors.append({"candidate_id": cid, "candidate_name": cand.candidate_name, "reason": str(exc), "retryable": True})
            continue
        drafts.append({
            "candidate_id": cid,
            "candidate_display_id": cand.display_id,
            "candidate_name": cand.candidate_name,
            "recipient_email": cand.email,
            "subject": generated["subject"],
            "body": generated["body"],
            "generated_at": datetime.utcnow().isoformat(),
        })
    return {"position_id": pos.id, "drafts": drafts, "errors": errors}


@router.post("/send")
def send_emails(req: EmailSendRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pos = get_jd(req.position_id, db)
    eligible, rejected = _shortlisted_candidates(db, pos.id, [e.candidate_id for e in req.emails])
    already_emailed = {
        cid for (cid,) in db.query(EmailRecord.candidate_id).filter(
            EmailRecord.position_id == pos.id,
            EmailRecord.candidate_id.in_(list(eligible)),
            EmailRecord.status.in_(SUCCESS_STATUSES),
        ).all()
    }

    results, skipped = [], list(rejected)
    seen = set()
    for draft in req.emails:
        cand = eligible.get(draft.candidate_id)
        if cand is None or draft.candidate_id in seen:
            continue
        seen.add(draft.candidate_id)
        subject, body = draft.subject.strip(), draft.body.strip()
        if not subject or not body:
            skipped.append({"candidate_id": cand.id, "candidate_name": cand.candidate_name, "reason": "Subject and body cannot be blank."})
            continue

        if draft.idempotency_key:
            existing = db.query(EmailRecord).filter(EmailRecord.idempotency_key == draft.idempotency_key).first()
            if existing:
                results.append({**_serialize_record(existing), "duplicate": True})
                continue
        if cand.id in already_emailed and not req.allow_resend:
            skipped.append({"candidate_id": cand.id, "candidate_name": cand.candidate_name,
                            "reason": "Already emailed for this requirement. Confirm a resend to send again.", "already_emailed": True})
            continue

        # Persist before delivering: the unique idempotency key stops a concurrent duplicate request
        # from sending a second copy, and the record survives a crash mid-delivery.
        record = EmailRecord(
            position_id=pos.id, position_display_id=pos.display_id, position_title=pos.title,
            candidate_id=cand.id, candidate_display_id=cand.display_id, candidate_name=cand.candidate_name,
            recipient_email=cand.email.strip(), subject=subject, body=body,
            status=EMAIL_STATUS_PENDING, delivery_mode=delivery_mode(),
            idempotency_key=draft.idempotency_key, sent_by=user.id,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(EmailRecord).filter(EmailRecord.idempotency_key == draft.idempotency_key).first()
            if existing:
                results.append({**_serialize_record(existing), "duplicate": True})
            continue

        record.status, record.delivery_mode, record.error = deliver_email(record.recipient_email, subject, body)
        db.commit()
        results.append({**_serialize_record(record), "duplicate": False})

    invalidate_email_cache()
    counts = {s: sum(1 for r in results if r["status"] == s and not r["duplicate"])
              for s in (EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED, EMAIL_STATUS_FAILED)}
    return {
        "position_id": pos.id,
        "delivery_mode": delivery_mode(),
        "sent_count": counts[EMAIL_STATUS_SENT],
        "simulated_count": counts[EMAIL_STATUS_SIMULATED],
        "failed_count": counts[EMAIL_STATUS_FAILED],
        "skipped_count": len(skipped),
        "results": results,
        "skipped": skipped,
    }


@router.get("/history")
def email_history_roles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cached = get_cache("email:history:roles")
    if cached is not None:
        return cached
    rows = (
        db.query(
            EmailRecord.position_id,
            func.count(EmailRecord.id),
            func.max(EmailRecord.created_at),
            func.sum(case((EmailRecord.status == EMAIL_STATUS_SENT, 1), else_=0)),
            func.sum(case((EmailRecord.status == EMAIL_STATUS_SIMULATED, 1), else_=0)),
            func.sum(case((EmailRecord.status == EMAIL_STATUS_FAILED, 1), else_=0)),
        )
        .group_by(EmailRecord.position_id)
        .order_by(func.max(EmailRecord.created_at).desc())
        .all()
    )
    pids = [r[0] for r in rows if r[0]]
    live = {p.id: p for p in db.query(Position).filter(Position.id.in_(pids)).all()} if pids else {}
    roles = []
    for pid, total, latest, sent, simulated, failed in rows:
        pos = live.get(pid)
        if pos is None:
            snap = db.query(EmailRecord).filter(EmailRecord.position_id == pid).order_by(EmailRecord.created_at.desc()).first()
        roles.append({
            "position_id": pid,
            "position_display_id": pos.display_id if pos else snap.position_display_id,
            "position_title": pos.title if pos else snap.position_title,
            "requirement_deleted": pos is None,
            "total_emails": total,
            "sent": sent or 0,
            "simulated": simulated or 0,
            "failed": failed or 0,
            "latest_at": latest.isoformat() if latest else None,
        })
    data = {"roles": roles}
    set_cache("email:history:roles", data, ttl_seconds=settings.CACHE_TTL_QUERY)
    return data


@router.get("/history/{position_id}")
def email_history_for_role(position_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cache_key = f"email:history:records:{position_id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records = (
        db.query(EmailRecord)
        .filter(EmailRecord.position_id == position_id)
        .order_by(EmailRecord.created_at.desc())
        .all()
    )
    data = {"position_id": position_id, "records": [_serialize_record(r) for r in records]}
    set_cache(cache_key, data, ttl_seconds=settings.CACHE_TTL_QUERY)
    return data


@router.get("/records/{record_id}")
def get_email_record(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.query(EmailRecord).filter(EmailRecord.id == record_id).first()
    if not record:
        raise HTTPException(404, "Email record not found.")
    return _serialize_record(record)


@router.post("/records/{record_id}/retry")
def retry_email_record(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Row lock where supported, so two concurrent retries cannot both deliver.
    record = db.query(EmailRecord).filter(EmailRecord.id == record_id).with_for_update().first()
    if not record:
        raise HTTPException(404, "Email record not found.")
    if record.status != EMAIL_STATUS_FAILED:
        raise HTTPException(409, f"Only failed emails can be retried (this one is '{record.status}').")
    record.status = EMAIL_STATUS_PENDING
    record.attempts = (record.attempts or 1) + 1
    db.commit()
    record.status, record.delivery_mode, record.error = deliver_email(record.recipient_email, record.subject, record.body)
    db.commit()
    invalidate_email_cache()
    return _serialize_record(record)
