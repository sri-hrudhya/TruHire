from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import require_role
from backend.database import get_db
from backend.models import ROLE_ADMIN, ROLE_RECRUITER, ROLES, User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSummary(BaseModel):
    id: str
    name: str
    email: str
    role: str


class RoleUpdateRequest(BaseModel):
    role: str


def _summary(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role or ROLE_RECRUITER}


@router.get("", response_model=List[UserSummary])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_role(ROLE_ADMIN))):
    return [_summary(u) for u in db.query(User).order_by(User.name).all()]


@router.patch("/{user_id}/role", response_model=UserSummary)
def set_role(user_id: str, req: RoleUpdateRequest, db: Session = Depends(get_db),
             admin: User = Depends(require_role(ROLE_ADMIN))):
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(ROLES)}.")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.role == ROLE_ADMIN and req.role != ROLE_ADMIN:
        admins = db.query(func.count(User.id)).filter(User.role == ROLE_ADMIN).scalar()
        if admins <= 1:
            raise HTTPException(status_code=409, detail="Cannot demote the last admin.")
    target.role = req.role
    db.commit()
    return _summary(target)
