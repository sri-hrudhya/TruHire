"""Tell a resume from a demand document (job description) by its content, not only its file name.

Each side has weighted signals; the higher total wins. Contact details (email + phone) are the
strongest sign of a resume, section headings like "Responsibilities" the strongest sign of a JD.
A demand document is still confirmed by the recruiter (category pick) before anything is created,
so a rare wrong guess is caught at that step.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from backend.services.ingestion.pii import EMAIL_REGEX, PHONE_REGEX

_JD_PHRASES: List[Tuple[str, int]] = [
    (r"job\s+description|\bjd\b", 3), (r"roles?\s*(and|&)\s*responsibilit\w+|key\s+responsibilit\w+|responsibilit\w+", 3),
    (r"we\s+are\s+(looking|hiring|seeking)|looking\s+for\s+(a|an)\b|the\s+ideal\s+candidate|you\s+will\b|you'?ll\b", 3),
    (r"(required|desired|preferred|mandatory)\s+(skills?|qualifications?|experience)|must[-\s]have|nice[-\s]to[-\s]have|good\s+to\s+have", 3),
    (r"about\s+the\s+(role|company|team|position)|who\s+you\s+are|what\s+you'?ll\s+do|why\s+join", 2),
    (r"no\.?\s*of\s+(positions|openings|vacancies)|openings?|vacanc\w+|\bclient\b|notice\s+period\s+(of|up\s+to|should)", 2),
    (r"\b\d+\s*\+?\s*(-|to)?\s*\d*\s*years?\s+of\s+(relevant\s+)?experience\s+(in|with|required)", 2),
    (r"apply\s+(now|today|with)|send\s+(your\s+)?(resume|cv)|share\s+(your\s+)?(resume|cv)", 2),
]
_RESUME_PHRASES: List[Tuple[str, int]] = [
    (r"curriculum\s+vitae|\bresume\b|\bcv\b", 2), (r"(work|professional|employment)\s+(experience|history)|career\s+summary", 3),
    (r"\beducation(al)?\s+(qualifications?|background)?\b|\bacademic\b", 2),
    (r"\bprojects?\b", 1), (r"certifications?|achievements?|declaration|references?\s+(available|on\s+request)", 2),
    (r"career\s+objective|professional\s+summary|\bobjective\b", 2),
    (r"linkedin\.com/in/|github\.com/|date\s+of\s+birth|\bdob\b|marital\s+status|languages?\s+known|nationality", 3),
    (r"\bi\s+(am|have|worked|led|built|developed|managed)\b|\bmy\s+(role|work|experience)\b", 2),
]
_JD_NAME = re.compile(r"\b(jd|job|requirement|demand|vacancy|opening|position|hiring)\b", re.IGNORECASE)
_RESUME_NAME = re.compile(r"\b(resume|cv|curriculum|profile)\b", re.IGNORECASE)


def _score(text: str, table: List[Tuple[str, int]]) -> int:
    return sum(weight for pattern, weight in table if re.search(pattern, text, re.IGNORECASE))


def detect_document_kind(filename: str, text: str) -> str:
    """Return "jd" or "resume"."""
    name = re.sub(r"[_\-.]+", " ", filename or "")
    body = (text or "")[:8000]
    jd = _score(body, _JD_PHRASES) + (4 if _JD_NAME.search(name) else 0)
    resume = _score(body, _RESUME_PHRASES) + (4 if _RESUME_NAME.search(name) else 0)
    # A candidate puts their own email and phone on the page; a JD rarely does.
    if EMAIL_REGEX.search(body) and PHONE_REGEX.search(body):
        resume += 5
    elif EMAIL_REGEX.search(body) or PHONE_REGEX.search(body):
        resume += 2
    if jd == resume:
        return "resume" if not body.strip() or len(body) < 1500 else "jd"  # long, signal-free prose reads as a spec
    return "jd" if jd > resume else "resume"
