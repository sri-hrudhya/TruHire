"""The New Demand form as data: its fields in form order, their types, options and validation.

Mirrors frontend/src/components/requirements/RequirementEditor.jsx (field order, labels, which are required) and
validates with the same pydantic schema the demand API uses (`JDDetails` / `PositionCreateRequest`), so the chat
assistant can never accept a value the New Demand page or the API would reject.

The form's Demand Status field is not offered in chat: a new demand starts as Open, and the other statuses need
a cancellation reason or linked resumes, which are set on the requirement itself.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.models import CLIENT_NAMES, DEFAULT_DEMAND_NAMES, Demand, canonical_demand_id
from backend.routers.job_descriptions import (
    MAX_DETAIL_CHARS, MAX_EXPERIENCE_YEARS, MAX_LOCATIONS, MAX_POSITIONS, JDDetails, PositionCreateRequest,
)

MAX_TEXT_CHARS = 100_000
SKIP_WORDS = re.compile(r"^(skip|none|n/?a|not stated|unknown|leave blank|no)$", re.I)

# key = the API payload field. `form_label` is what the New Demand page shows. Order is the form's order.
FIELDS: List[Dict[str, Any]] = [
    {"key": "title", "label": "Title", "type": "text", "required": True, "prompt": "What is the demand title?", "max": MAX_DETAIL_CHARS},
    {"key": "demand_id", "label": "Demand Practice", "type": "select", "required": True, "prompt": "Select the Demand Practice."},
    {"key": "client_name", "label": "Client Name", "type": "select_or_text", "required": False,
     "prompt": "Select the Client Name, or type a different client.", "max": MAX_DETAIL_CHARS},
    {"key": "experience_years", "label": "Min Experience (years)", "type": "number", "required": False,
     "prompt": "What is the minimum experience, in years?", "min": 0, "max": MAX_EXPERIENCE_YEARS, "step": 0.5},
    {"key": "experience_max_years", "label": "Max Experience (years)", "type": "number", "required": False,
     "prompt": "What is the maximum experience, in years?", "min": 0, "max": MAX_EXPERIENCE_YEARS, "step": 0.5},
    {"key": "locations", "label": "Locations", "type": "tags", "required": False,
     "prompt": f"Which locations apply? Add up to {MAX_LOCATIONS}, separated by commas.", "max": MAX_LOCATIONS},
    {"key": "no_of_positions", "label": "No. of Positions", "type": "number", "required": False, "default": 1,
     "prompt": "How many positions are you hiring for?", "min": 0, "max": MAX_POSITIONS, "step": 1},
    {"key": "start_date", "label": "Start Date", "type": "date", "required": False, "prompt": "What is the start date?"},
    {"key": "end_date", "label": "End Date (tentative)", "type": "date", "required": False, "prompt": "What is the tentative end date?"},
    {"key": "jd_text", "label": "Specification", "type": "textarea", "required": True,
     "prompt": "Paste or type the demand specification.", "max": MAX_TEXT_CHARS},
]
BY_KEY = {f["key"]: f for f in FIELDS}
KEYS = [f["key"] for f in FIELDS]
REQUIRED_KEYS = [f["key"] for f in FIELDS if f["required"]]


def practice_options(db: Session) -> List[Dict[str, str]]:
    """The practices the New Demand page offers (GET /api/demands): the five fixed ones, in order."""
    rows = {d.id: d for d in db.query(Demand).filter(Demand.id.in_([canonical_demand_id(n) for n in DEFAULT_DEMAND_NAMES])).all()}
    return [{"value": canonical_demand_id(n), "label": rows[canonical_demand_id(n)].name if canonical_demand_id(n) in rows else n}
            for n in DEFAULT_DEMAND_NAMES]


def field_definitions(db: Session) -> List[Dict[str, Any]]:
    """Field definitions for the client, with the live option lists filled in."""
    out = []
    for f in FIELDS:
        d = dict(f)
        if f["key"] == "demand_id":
            d["options"] = practice_options(db)
        elif f["key"] == "client_name":
            d["options"] = [{"value": c, "label": c} for c in CLIENT_NAMES]
        out.append(d)
    return out


def _parse_date(raw: Any) -> date:
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("Enter a valid date, for example 2026-11-15.")


def _schema_error(exc: ValidationError, key: str) -> str:
    err = exc.errors()[0]
    msg = str(err.get("msg", "Invalid value.")).replace("Value error, ", "")
    return msg[:1].upper() + msg[1:]


def _check_details(values: Dict[str, Any]) -> Dict[str, str]:
    """Run the demand API's own schema over the detail fields; returns {field: message}."""
    payload = {k: v for k, v in values.items() if k in JDDetails.model_fields and v is not None}
    try:
        JDDetails(**payload)
        return {}
    except ValidationError as exc:
        errors: Dict[str, str] = {}
        for err in exc.errors():
            loc = err.get("loc") or ()
            msg = str(err.get("msg", "Invalid value.")).replace("Value error, ", "")
            msg = msg[:1].upper() + msg[1:]
            if loc and loc[0] in BY_KEY:
                errors.setdefault(loc[0], msg)
            elif "end_date" in msg.lower():
                errors.setdefault("end_date", msg)
            elif "max experience" in msg.lower():
                errors.setdefault("experience_max_years", msg)
            else:
                errors.setdefault("title", msg)
        return errors


def normalize(key: str, raw: Any, db: Session) -> Tuple[Any, Optional[str]]:
    """Turn what the user entered into the stored value. Returns (value, error); value None means "left blank"."""
    field = BY_KEY[key]
    kind = field["type"]
    blank = raw is None or (isinstance(raw, str) and not raw.strip()) or (isinstance(raw, list) and not raw)
    if not blank and isinstance(raw, str) and not field["required"] and kind != "textarea" and SKIP_WORDS.match(raw.strip()):
        blank = True
    if blank:
        return (None, f"{field['label']} is required.") if field["required"] else (None, None)
    try:
        if kind in ("text", "textarea"):
            text = " ".join(str(raw).split()) if kind == "text" else str(raw).strip()
            if len(text) > field["max"]:
                return None, f"{field['label']} is limited to {field['max']} characters."
            return text, None
        if kind == "select":
            options = practice_options(db)
            wanted = str(raw).strip().lower()
            hit = next((o for o in options if wanted in (o["value"].lower(), o["label"].lower())), None)
            if not hit:
                return None, "Choose one of: " + ", ".join(o["label"] for o in options) + "."
            return hit["value"], None
        if kind == "select_or_text":
            text = " ".join(str(raw).split())
            value = next((c for c in CLIENT_NAMES if c.lower() == text.lower()), text)
            return (value, None) if len(value) <= field["max"] else (None, f"Client name is limited to {field['max']} characters.")
        if kind == "number":
            number = float(str(raw).strip().replace(",", "")) if not isinstance(raw, (int, float)) else float(raw)
            if key == "no_of_positions":
                if number != int(number):
                    return None, "No. of Positions must be a whole number."
                number = int(number)
            elif number == int(number):
                number = int(number)
            errors = _check_details({key: number})
            return (None, errors[key]) if key in errors else (number, None)
        if kind == "tags":
            items = raw if isinstance(raw, list) else re.split(r"[,;]+", str(raw))
            errors = _check_details({"locations": [str(i) for i in items]})
            if "locations" in errors:
                return None, errors["locations"]
            places = JDDetails(locations=[str(i) for i in items]).locations
            return places or None, None
        if kind == "date":
            value = _parse_date(raw)
            errors = _check_details({key: value})
            return (None, errors[key]) if key in errors else (value.isoformat(), None)
    except ValidationError as exc:
        return None, _schema_error(exc, key)
    except ValueError as exc:
        text = str(exc)
        return None, text if kind == "date" else f"{field['label']} must be a number."
    return None, "Invalid value."


def cross_check(values: Dict[str, Any]) -> Dict[str, str]:
    """Rules that span fields (max >= min experience, end after start) over everything collected so far."""
    return _check_details(values)


def display(key: str, value: Any, db: Session) -> str:
    if value is None or value == "" or value == []:
        return "Not provided"
    if key == "demand_id":
        return next((o["label"] for o in practice_options(db) if o["value"] == value), str(value))
    if key == "locations":
        return ", ".join(value)
    if key in ("experience_years", "experience_max_years"):
        return f"{value:g} yrs" if isinstance(value, (int, float)) else str(value)
    if key in ("start_date", "end_date"):
        try:
            return date.fromisoformat(str(value)).strftime("%d %b %Y")
        except ValueError:
            return str(value)
    return str(value)


def build_request(values: Dict[str, Any]) -> PositionCreateRequest:
    """The demand API's own request model, built from collected values. Raises ValidationError if anything is off."""
    payload = {k: v for k, v in values.items() if v is not None and k in PositionCreateRequest.model_fields}
    return PositionCreateRequest(**payload)
