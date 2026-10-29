"""Deterministic JD -> Demand category classification (no external AI).

Every requirement belongs to exactly one of five fixed categories: Java, GenAI, Camunda, Pega, Others.

Rules
-----
* Each specialist category has weighted keyword patterns. A "primary" term (e.g. "Camunda") weighs 3,
  a supporting term (e.g. "Spring Boot") weighs 1-2.
* A term's contribution is weight x min(occurrences, 5); occurrences in the title count 3x, so a title
  can steer an ambiguous body but never outvote a body that is clearly about something else.
* A category qualifies only when its score >= MIN_SCORE (a lone passing mention of a skill in a long
  skills list is not enough). No qualifying category -> "Others".
* The highest score wins. Ties are broken by PRIORITY: Camunda > Pega > GenAI > Java (most specific
  first; Java is the generic skill that Camunda/Pega/GenAI postings routinely mention too).
* The file name is never used; for uploads the extracted document text is what gets classified.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from backend.models import DEFAULT_DEMAND_NAMES, OTHERS_DEMAND_NAME

CATEGORIES = DEFAULT_DEMAND_NAMES  # single source of truth lives in models.py
OTHERS = OTHERS_DEMAND_NAME
MIN_SCORE = 4
MAX_COUNT = 5
TITLE_MULTIPLIER = 3

# Tie-break order, most specific first.
PRIORITY = ("Camunda", "Pega", "GenAI", "Java")

# (regex, weight). Patterns use \b so "java" never matches "javascript".
_RULES: Dict[str, list] = {
    "Camunda": [
        (r"\bcamunda\b", 3), (r"\bzeebe\b", 3), (r"\bbpmn\b", 2), (r"\bdmn\b", 1),
        (r"\bprocess (?:orchestration|automation) engine\b", 1), (r"\bworkflow engine\b", 1),
    ],
    "Pega": [
        (r"\bpega(?:systems)?\b", 3), (r"\bprpc\b", 3), (r"\bclsa\b", 2), (r"\bcssa\b", 2),
        (r"\bpega (?:cdh|infinity|constellation|platform)\b", 1),
    ],
    "GenAI": [
        (r"\bgen ?ai\b", 3), (r"\bgenerative ai\b", 3), (r"\bllms?\b", 3), (r"\blarge language models?\b", 3),
        (r"\blangchain\b", 2), (r"\bllama ?index\b", 2), (r"\brag\b", 2), (r"\bretrieval[- ]augmented\b", 2),
        (r"\bprompt engineering\b", 2), (r"\bopenai\b", 2), (r"\bgpt(?:-?\d)?\b", 1), (r"\bvector (?:db|database|store)s?\b", 1),
        (r"\bembeddings?\b", 1), (r"\bhugging ?face\b", 1), (r"\bfoundation models?\b", 2), (r"\bagentic\b", 1),
    ],
    "Java": [
        (r"\bjava\b", 3), (r"\bj2ee\b", 3), (r"\bjava ?ee\b", 3), (r"\bjakarta ee\b", 3), (r"\bspring ?boot\b", 2),
        (r"\bspring (?:framework|mvc|cloud|security|data)\b", 2), (r"\bhibernate\b", 2), (r"\bjvm\b", 2),
        (r"\bjpa\b", 1), (r"\bmaven\b", 1), (r"\bgradle\b", 1), (r"\bjunit\b", 1), (r"\bservlets?\b", 1),
    ],
}
_COMPILED = {cat: [(re.compile(p, re.IGNORECASE), w) for p, w in rules] for cat, rules in _RULES.items()}


@dataclass
class Classification:
    category: str
    scores: Dict[str, int] = field(default_factory=dict)
    confident: bool = True
    note: Optional[str] = None


def _score(category: str, title: str, body: str) -> int:
    total = 0
    for pattern, weight in _COMPILED[category]:
        count = min(len(pattern.findall(body)), MAX_COUNT) + TITLE_MULTIPLIER * min(len(pattern.findall(title)), MAX_COUNT)
        total += weight * count
    return total


def classify_jd_detailed(title: Optional[str], jd_text: Optional[str]) -> Classification:
    title, body = (title or ""), (jd_text or "")
    if not body.strip() and not title.strip():
        return Classification(OTHERS, {}, False, "No readable content to classify; filed under Others.")
    scores = {cat: _score(cat, title, body) for cat in PRIORITY}
    qualifying = {c: s for c, s in scores.items() if s >= MIN_SCORE}
    if not qualifying:
        return Classification(OTHERS, scores, False,
                              "Could not clearly match Java, GenAI, Camunda or Pega; filed under Others.")
    best = max(qualifying.values())
    category = next(c for c in PRIORITY if qualifying.get(c) == best)
    return Classification(category, scores, True)


def matches_category(category: str, job_titles: Optional[list], skills: Optional[list], resume_text: Optional[str]) -> bool:
    """Does a candidate profile qualify for `category`? Same weighted rules as JDs, but a candidate may
    qualify for several (a Camunda developer who also knows Java is both). 'Others' means no
    specialist category qualifies. Titles count as the title, skills + resume text as the body."""
    title = " ".join(job_titles or [])
    body = " ".join(skills or []) + "\n" + (resume_text or "")
    if category == OTHERS:
        return classify_jd_detailed(title, body).category == OTHERS
    if category not in _COMPILED:
        return False
    return _score(category, title, body) >= MIN_SCORE


def classify_jd(title: Optional[str], jd_text: Optional[str]) -> str:
    return classify_jd_detailed(title, jd_text).category
