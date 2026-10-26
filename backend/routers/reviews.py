"""Shared review workflow: who reviews a candidate for a requirement, and the comment thread on a candidate."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.auth import get_current_user, require_role
from backend.config import settings
from backend.database import get_db
from backend.models import (
    ROLE_ADMIN, Candidate, CandidateAssignment, CandidateComment, Position, User,
)

router = APIRouter(prefix="/api", tags=["reviews"])


def _clean_body(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("Comment cannot be empty.")
    if len(v) > settings.COMMENT_MAX_CHARS:
        raise ValueError(f"Comment is limited to {settings.COMMENT_MAX_CHARS} characters.")
    return v


class AssignmentRequest(BaseModel):
    assignee_id: str


class CommentRequest(BaseModel):
    body: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    position_id: Optional[str] = None

    _check_body = field_validator("body")(_clean_body)


class CommentUpdateRequest(BaseModel):
    body: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("body")
    @classmethod
    def _check_body(cls, v):
        return v if v is None else _clean_body(v)


def _person(u: Optional[User]) -> Optional[dict]:
    return {"id": u.id, "name": u.name} if u else None


def _assignment_dict(a: CandidateAssignment, db: Session) -> dict:
    assignee = db.query(User).filter(User.id == a.assignee_id).first()
    return {"position_id": a.position_id, "candidate_id": a.candidate_id, "assignee": _person(assignee),
            "assigned_by": a.assigned_by, "created_at": a.created_at.isoformat() if a.created_at else None}


def _require_jd_and_candidate(db: Session, pid: str, cid: str) -> None:
    if not db.query(Position.id).filter(Position.id == pid).first():
        raise HTTPException(404, "Requirement not found.")
    if not db.query(Candidate.id).filter(Candidate.id == cid).first():
        raise HTTPException(404, "Candidate not found.")


@router.put("/job-descriptions/{pid}/candidates/{cid}/assignment")
def assign_candidate(pid: str, cid: str, req: AssignmentRequest, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    _require_jd_and_candidate(db, pid, cid)
    if not db.query(User.id).filter(User.id == req.assignee_id).first():
        raise HTTPException(404, "Assignee not found.")
    row = db.query(CandidateAssignment).filter_by(position_id=pid, candidate_id=cid).first()
    # Admins assign anyone; a recruiter may only take an unassigned candidate (or keep their own).
    claims_for_self = req.assignee_id == user.id and (row is None or row.assignee_id == user.id)
    if user.role != ROLE_ADMIN and not claims_for_self:
        raise HTTPException(403, "Only an admin can assign a candidate to someone else.")
    if row is None:
        row = CandidateAssignment(position_id=pid, candidate_id=cid)
        db.add(row)
    row.assignee_id = req.assignee_id
    row.assigned_by = user.id
    row.created_at = datetime.utcnow()
    db.commit()
    return _assignment_dict(row, db)


@router.delete("/job-descriptions/{pid}/candidates/{cid}/assignment")
def unassign_candidate(pid: str, cid: str, db: Session = Depends(get_db),
                       admin: User = Depends(require_role(ROLE_ADMIN))):
    row = db.query(CandidateAssignment).filter_by(position_id=pid, candidate_id=cid).first()
    if row is None:
        raise HTTPException(404, "No assignment to remove.")
    db.delete(row)
    db.commit()
    return {"position_id": pid, "candidate_id": cid, "assignee": None}


@router.get("/job-descriptions/{pid}/assignments")
def list_assignments(pid: str, mine: bool = False, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    if not db.query(Position.id).filter(Position.id == pid).first():
        raise HTTPException(404, "Requirement not found.")
    q = db.query(CandidateAssignment).filter(CandidateAssignment.position_id == pid)
    if mine:
        q = q.filter(CandidateAssignment.assignee_id == user.id)
    return [_assignment_dict(a, db) for a in q.all()]


def _can_manage(user: User, comment: CandidateComment) -> bool:
    return user.role == ROLE_ADMIN or comment.author_id == user.id


def _comment_dict(c: CandidateComment, viewer: User) -> dict:
    return {"id": c.id, "candidate_id": c.candidate_id, "position_id": c.position_id, "author": _person(c.author),
            "body": c.body, "rating": c.rating,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "edited_at": c.edited_at.isoformat() if c.edited_at else None,
            "can_edit": _can_manage(viewer, c)}


@router.get("/candidates/{cid}/comments")
def list_comments(cid: str, position_id: Optional[str] = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    if not db.query(Candidate.id).filter(Candidate.id == cid).first():
        raise HTTPException(404, "Candidate not found.")
    q = db.query(CandidateComment).filter(CandidateComment.candidate_id == cid)
    if position_id:
        q = q.filter(CandidateComment.position_id == position_id)
    return [_comment_dict(c, user) for c in q.order_by(CandidateComment.created_at).all()]


@router.post("/candidates/{cid}/comments")
def add_comment(cid: str, req: CommentRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.query(Candidate.id).filter(Candidate.id == cid).first():
        raise HTTPException(404, "Candidate not found.")
    if req.position_id and not db.query(Position.id).filter(Position.id == req.position_id).first():
        raise HTTPException(404, "Requirement not found.")
    row = CandidateComment(candidate_id=cid, position_id=req.position_id, author_id=user.id,
                           body=req.body, rating=req.rating)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _comment_dict(row, user)


def _comment_or_error(db: Session, comment_id: str, user: User) -> CandidateComment:
    row = db.query(CandidateComment).filter(CandidateComment.id == comment_id).first()
    if row is None:
        raise HTTPException(404, "Comment not found.")
    if not _can_manage(user, row):
        raise HTTPException(403, "Only the author or an admin can change this comment.")
    return row


@router.patch("/comments/{comment_id}")
def update_comment(comment_id: str, req: CommentUpdateRequest, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    row = _comment_or_error(db, comment_id, user)
    if req.body is not None:
        row.body = req.body
    if req.rating is not None:
        row.rating = req.rating
    row.edited_at = datetime.utcnow()
    db.commit()
    return _comment_dict(row, user)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = _comment_or_error(db, comment_id, user)
    db.delete(row)
    db.commit()
    return {"id": comment_id}
