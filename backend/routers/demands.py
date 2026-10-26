from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import DEFAULT_DEMAND_NAMES, canonical_demand_id, demand_display_id, Demand, Position, User

router = APIRouter(prefix="/api/demands", tags=["demands"])


class DemandCreateRequest(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class DemandUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class DemandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    jd_count: int = 0
    is_default: bool = False
    display_id: Optional[str] = None
    created_by_name: Optional[str] = None


class DemandJD(BaseModel):
    id: str
    display_id: Optional[str] = None
    title: str
    jd_version: int
    created_at: datetime


class DemandDetailResponse(DemandResponse):
    job_descriptions: List[DemandJD] = []


def _get_demand(demand_id: str, db: Session) -> Demand:
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(404, "Demand not found.")
    return demand


def _jds_of(demand_id: str, db: Session) -> List[Position]:
    return db.query(Position).filter(Position.demand_id == demand_id).order_by(Position.created_at.desc()).all()


_DEFAULT_LOWER = [n.lower() for n in DEFAULT_DEMAND_NAMES]


def _is_default(demand: Demand) -> bool:
    return (demand.name or "").strip().lower() in _DEFAULT_LOWER


def _serialize(demand: Demand, jd_count: int, creator_name: Optional[str] = None) -> dict:
    return {"display_id": demand_display_id(demand.id), "created_by_name": creator_name,  # None for system-seeded demands
            "is_default": _is_default(demand), "id": demand.id, "name": demand.name, "description": demand.description, "created_by": demand.created_by,
            "created_at": demand.created_at, "updated_at": demand.updated_at, "jd_count": jd_count}


def _serialize_jd(p: Position) -> dict:
    return {"id": p.id, "display_id": p.display_id, "title": p.title, "jd_version": p.jd_version, "created_at": p.created_at}


@router.get("", response_model=List[DemandResponse])
def list_demands(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    counts = dict(db.query(Position.demand_id, func.count(Position.id)).filter(Position.demand_id.isnot(None)).group_by(Position.demand_id).all())
    # Only the five canonical categories are ever exposed, in their fixed order.
    demands = db.query(Demand).filter(Demand.id.in_([canonical_demand_id(n) for n in DEFAULT_DEMAND_NAMES])).all()
    demands.sort(key=lambda d: _DEFAULT_LOWER.index(d.name.strip().lower()))
    names = dict(db.query(User.id, User.name).all())
    return [_serialize(d, counts.get(d.id, 0), names.get(d.created_by)) for d in demands]


@router.post("", response_model=DemandResponse)
def create_demand(req: DemandCreateRequest, user: User = Depends(get_current_user)):
    raise HTTPException(403, "Demand categories are fixed (" + ", ".join(DEFAULT_DEMAND_NAMES) + "); JDs are categorised automatically.")


@router.get("/{demand_id}", response_model=DemandDetailResponse)
def get_demand(demand_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = _get_demand(demand_id, db)
    jds = _jds_of(demand_id, db)
    creator = db.query(User.name).filter(User.id == demand.created_by).scalar() if demand.created_by else None
    return {**_serialize(demand, len(jds), creator), "job_descriptions": [_serialize_jd(p) for p in jds]}


@router.get("/{demand_id}/job-descriptions", response_model=List[DemandJD])
def list_demand_job_descriptions(demand_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_demand(demand_id, db)
    return [_serialize_jd(p) for p in _jds_of(demand_id, db)]


@router.put("/{demand_id}", response_model=DemandResponse)
def update_demand(demand_id: str, req: DemandUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_demand(demand_id, db)
    raise HTTPException(400, "Demand categories cannot be renamed or edited.")


@router.delete("/{demand_id}")
def delete_demand(demand_id: str, detach_jds: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_demand(demand_id, db)
    raise HTTPException(400, "Demand categories cannot be deleted.")
