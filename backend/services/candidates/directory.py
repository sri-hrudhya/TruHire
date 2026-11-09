"""Bounded, database-backed candidate directory lookup shared by UI and chat."""
from sqlalchemy import case, or_

from backend.models import Candidate


def filter_directory(query, raw: str):
    """Match partial name, email, phone, display ID, or stated current company.

    Any token can match any field; rows matching more tokens rank first. Callers apply
    a bounded SQL limit/offset rather than loading the full pool into application memory.
    """
    terms = list(dict.fromkeys(part.strip() for part in (raw or "").split() if len(part.strip()) >= 2))[:8]
    if not terms:
        return query.order_by(Candidate.uploaded_at.desc())
    conditions, scores = [], []
    for term in terms:
        digits = "".join(ch for ch in term if ch.isdigit())
        match = or_(Candidate.display_id.ilike(f"%{term}%"),
                    Candidate.candidate_name.ilike(f"%{term}%"),
                    Candidate.email.ilike(f"%{term}%"),
                    Candidate.email_norm.ilike(f"%{term.casefold()}%"),
                    Candidate.current_company.ilike(f"%{term}%"))
        if digits:
            match = or_(match, Candidate.phone_norm.ilike(f"%{digits}%"), Candidate.phone.ilike(f"%{term}%"))
        conditions.append(match)
        scores.append(case((match, 1), else_=0))
    return query.filter(or_(*conditions)).order_by(sum(scores).desc(), Candidate.uploaded_at.desc(), Candidate.id)
