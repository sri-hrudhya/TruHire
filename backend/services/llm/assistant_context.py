"""Grounding for the chat assistant: what the product's words mean, plus a compact snapshot of saved data.

The definitions mirror backend/models.py (Demand, Position, CLIENT_NAMES, JD_STATUSES). Counts and records
come from the database at request time, so the model never has to guess them. Reads are the same ones the
Requirements page uses (`GET /api/jds`, `GET /api/demands`): every signed-in user sees every requirement.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from backend.models import DEFAULT_DEMAND_NAMES, INACTIVE_JD_STATUSES, JD_STATUSES, LEGACY_JD_STATUS_ALIASES, Position

MAX_LISTED_REQUIREMENTS = 10
MAX_JD_CHARS = 600
NO_CLIENT = "No client assigned"

GLOSSARY = (
    "TERMINOLOGY (authoritative for this product):\n"
    f"- Practice: one of the fixed folders {', '.join(DEFAULT_DEMAND_NAMES)}. It groups demands by skill area. "
    "Practices are system data; users cannot add or rename them. (In the database a practice is a `Demand` row.)\n"
    "- Demand / requirement / JD: one hiring need (a job description, id like TRU-JD-12). The words are "
    "interchangeable. A demand is filed under at most one practice and has an optional client, status "
    f"({', '.join(JD_STATUSES)}), role, location, experience range, number of positions and start/end dates.\n"
    "- Client: the customer a demand is for (a name on the demand). A client is not a practice: one client can "
    "have demands in several practices, and a practice holds demands for several clients.\n"
    "- Positions: the number of people to hire for one demand, not a count of demands.\n"
    "- Cancelled demands stay on record but are not counted as live."
)

RULES = (
    "ANSWERING RULES:\n"
    "- Use only the DATA below and the TERMINOLOGY above. Never invent clients, practices, demands, statuses, dates or counts.\n"
    "- If the DATA does not contain what was asked (for example a field that is empty, or a record not listed), say exactly "
    "what is missing instead of guessing. The listed requirements are only a sample; the counts are complete.\n"
    "- If the question is ambiguous (for example it could mean a practice or a client, or names no requirement when "
    "several fit), ask one short clarifying question and stop.\n"
    "- Read terse messages by their obvious meaning. \"practices\" / \"no. of practices\" / \"total practices\" = the Demand Practices with "
    "their live demand counts; \"clients\" = clients with their live demand counts; \"demands\" / \"total demands\" = demand totals "
    "(say live and cancelled). Answer directly from DATA; do not ask what they mean when one reading is clearly most likely, "
    "and mention the other reading in a short closing line if it could matter.\n"
    "- Sound like a helpful colleague: lead with the answer, then at most one useful follow-up offer. No boilerplate, "
    "no repeating the question, no apologies.\n"
    "- Keep answers short. Use a brief list or a few lines for multi-part answers; no preamble.\n"
    "- Do not claim to have done an action (creating, emailing, updating) unless the user used the attach or choice controls in this chat."
)


def _status(position: Position) -> str:
    raw = position.status or "Open"
    return LEGACY_JD_STATUS_ALIASES.get(raw, raw)


def _client(position: Position) -> str:
    return (position.client_name or "").strip() or NO_CLIENT


def _practice(position: Position) -> str:
    return position.demand.name if position.demand else "No practice assigned"


def _terms(message: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", (message or "").lower()) if t not in _STOP]


_STOP = {
    "the", "and", "for", "are", "how", "many", "what", "which", "show", "list", "tell", "about", "with", "from",
    "demand", "demands", "requirement", "requirements", "practice", "practices", "client", "clients", "jd", "jds",
    "please", "can", "you", "does", "this", "that", "there", "have", "has", "open", "all", "any",
}


def _relevant(positions: List[Position], message: str, position_id: Optional[str]) -> List[Position]:
    """Requirements the question is about (by id, practice, client or title words); the newest ones otherwise."""
    lowered = (message or "").lower()
    ids = {m.upper() for m in re.findall(r"\bTRU-JD-\d+\b", message or "", re.I)}
    picked = [p for p in positions if p.id == position_id or (p.display_id or "").upper() in ids]
    if not picked:
        names = {_practice(p).lower() for p in positions} | {_client(p).lower() for p in positions if _client(p) != NO_CLIENT}
        named = {n for n in names if n and re.search(rf"\b{re.escape(n)}\b", lowered)}
        terms = _terms(message)
        picked = [p for p in positions if (named and ({_practice(p).lower(), _client(p).lower()} & named))
                  or (terms and any(t in (p.title or "").lower() for t in terms))]
    return (picked or positions)[:MAX_LISTED_REQUIREMENTS]


def build_data_context(db: Session, message: str, position_id: Optional[str] = None) -> dict:
    """Complete counts per practice, client and status, plus a few requirements relevant to `message`."""
    positions = db.query(Position).options(joinedload(Position.demand)).order_by(Position.created_at.desc()).all()
    live = [p for p in positions if _status(p) not in INACTIVE_JD_STATUSES]

    per_practice = {name: Counter() for name in DEFAULT_DEMAND_NAMES}
    for p in positions:
        per_practice.setdefault(_practice(p), Counter())[_status(p)] += 1
    clients: dict = {}
    for p in live:
        by_practice = clients.setdefault(_client(p), Counter())
        by_practice[_practice(p)] += 1

    def row(p: Position, with_text: bool) -> dict:
        item = {
            "id": p.display_id, "title": p.title, "practice": _practice(p), "client": p.client_name or None,
            "status": _status(p), "role": p.role, "locations": p.locations or ([p.location] if p.location else None),
            "experience_years": p.experience_years, "experience_max_years": p.experience_max_years,
            "positions_to_hire": p.no_of_positions, "start_date": p.start_date, "end_date": p.end_date,
        }
        if with_text:
            item["jd_text"] = (p.jd_text or "")[:MAX_JD_CHARS]
        return {k: v for k, v in item.items() if v not in (None, "", [])}

    relevant = _relevant(positions, message, position_id)
    return {
        "totals": {"all_requirements": len(positions), "live_requirements": len(live), "cancelled": len(positions) - len(live)},
        "practices": {name: dict(counts) for name, counts in per_practice.items()},
        "live_requirements_by_client": {name: dict(counts) for name, counts in sorted(clients.items(), key=lambda kv: (kv[0] == NO_CLIENT, kv[0].casefold()))},
        "listed_requirements": [row(p, with_text=len(relevant) <= 3) for p in relevant],
        "listed_note": f"{len(relevant)} of {len(positions)} requirements shown",
    }
