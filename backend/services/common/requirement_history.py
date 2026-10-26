"""Persistent requirement history: one row per JD creation, update, status change or deletion.

Entries are added to the caller's session so they commit atomically with the change they describe.
"""
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from backend.models import DEFAULT_DEMAND_NAMES, Position, RequirementHistory, User, canonical_demand_id, demand_display_id


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def snapshot(pos: Position, fields: Iterable[str]) -> Dict[str, Any]:
    return {f: _plain(getattr(pos, f)) for f in fields}


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Fields whose value differs, as {field: {old, new}}."""
    return {k: {"old": before.get(k), "new": after[k]} for k in after if before.get(k) != after[k]}


def record(db: Session, action: str, pos: Position, user: Optional[User], changes: Optional[Dict[str, Any]] = None,
           user_name: Optional[str] = None) -> None:
    demand_name = next((n for n in DEFAULT_DEMAND_NAMES if canonical_demand_id(n) == pos.demand_id), None)
    db.add(RequirementHistory(
        action=action, item_type="jd", item_id=pos.id, item_display_id=pos.display_id, item_title=pos.title,
        demand_id=pos.demand_id, demand_display_id=demand_display_id(pos.demand_id), demand_name=demand_name,
        user_id=user.id if user else None, user_name=(user.name if user else user_name) or "System", changes=changes or None,
    ))


def serialize(row: RequirementHistory) -> Dict[str, Any]:
    return {
        "id": row.id, "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,  # stored naive-UTC
        "action": row.action, "item_type": row.item_type, "item_id": row.item_id,
        "item_display_id": row.item_display_id, "item_title": row.item_title,
        "demand_id": row.demand_id, "demand_display_id": row.demand_display_id, "demand_name": row.demand_name,
        "user_id": row.user_id, "user_name": row.user_name, "changes": row.changes or {},
    }
