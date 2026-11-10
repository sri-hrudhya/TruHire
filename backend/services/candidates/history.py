"""Which requirements a candidate was submitted to, and each one's current status.

A requirement appears only when a recruiter set a status for the candidate on it. Automatic match
scores and review assignments are not submissions and are never shown here.

Shared by the candidate history API, the history directory and the chat assistant so all three
show the same "Client - Status | last modified | modified by" rows.
"""
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from backend.models import Position, RequirementCandidateStatus, User


def _row(position: Position, status: str, when, actor) -> dict:
    return {"id": position.id, "display_id": position.display_id, "title": position.title,
            "client_name": position.client_name, "demand_owner": position.demand_owner, "status": status,
            "last_modified": when.isoformat() if when else None, "modified_by": actor.name if actor else None}


def requirement_rows(db: Session, candidate_ids: Iterable[str]) -> Dict[str, List[dict]]:
    """Per candidate, one row per requirement a recruiter set a status on, newest change first."""
    ids = list(dict.fromkeys(candidate_ids))
    rows: Dict[str, List[dict]] = {cid: [] for cid in ids}
    if not ids:
        return rows
    for status, position, actor in (db.query(RequirementCandidateStatus, Position, User)
                                    .join(Position, Position.id == RequirementCandidateStatus.position_id)
                                    .outerjoin(User, User.id == RequirementCandidateStatus.updated_by)
                                    .filter(RequirementCandidateStatus.candidate_id.in_(ids))
                                    .order_by(RequirementCandidateStatus.updated_at.desc()).all()):
        rows[status.candidate_id].append(_row(position, status.status, status.updated_at, actor))
    for items in rows.values():
        items.sort(key=lambda item: item["last_modified"] or "", reverse=True)
    return rows
