"""
App-level policy layer on top of laya_service: composes Laya's fast typed decisions with
TruHire's existing deterministic scoring, and decides when a question is cheap enough for
Laya alone versus when it must escalate to the vLLM LLM path. Nothing here changes the
existing deterministic formulas in scoring.py/ai_service.py — Laya only adds a bounded
signal on top, or is skipped entirely (falling back to today's behavior) when unavailable
or unconfident.
"""
import hashlib
from typing import List, Optional, Tuple

from backend.config import settings
from backend.models import Candidate, CandidateMatch, Position
from backend.services.common.cache import get_cache, set_cache
from backend.services.common.ai_audit import ai_feature
from backend.services.llm.laya_service import LayaUnavailable, ask_score_batch

RERANK_QUESTION = "How strong is this candidate's overall fit for this job description?"

def _cache_key(*parts: str) -> str:
    digest = hashlib.sha256("||".join(parts).encode("utf-8", "ignore")).hexdigest()
    return f"decision:{digest}"


def _candidate_state(candidate: Candidate, jd_title: str, jd_text: str) -> str:
    return (
        f"Candidate skills: {', '.join(candidate.extracted_skills or [])}\n"
        f"Experience: {candidate.years_experience} years\n"
        f"Education: {candidate.education or 'Not specified'}\n\n"
        f"Job Title: {jd_title}\nJob Description:\n{jd_text[:4000]}"
    )


def _blend(deterministic_score: float, laya_pct: float, raw: dict) -> Tuple[float, dict]:
    blended = ((1 - settings.LAYA_RERANK_WEIGHT) * deterministic_score) + (settings.LAYA_RERANK_WEIGHT * laya_pct)
    return round(blended, 1), {"laya_fit_score": round(laya_pct, 1), "raw": raw}


def rerank_scores_batch(items: List[Tuple[float, Candidate, Position]]) -> List[Tuple[float, Optional[dict]]]:
    """
    One shared Laya forward pass for every candidate in
    the retrieval pool that isn't already cached, instead of one call per candidate.
    Returns (blended_score, laya_signal) per input item, in the same order.
    """
    if not items:
        return []

    results: List[Optional[Tuple[float, Optional[dict]]]] = [None] * len(items)
    to_query: List[int] = []
    for i, (deterministic_score, candidate, position) in enumerate(items):
        cache_key = _cache_key("rerank", candidate.file_hash, position.id, str(position.jd_version))
        cached = get_cache(cache_key)
        if cached is not None:
            laya_pct, raw = cached
            results[i] = _blend(deterministic_score, laya_pct, raw)
        else:
            to_query.append(i)

    if to_query:
        states = [_candidate_state(items[i][1], items[i][2].title, items[i][2].jd_text) for i in to_query]
        try:
            with ai_feature("laya_rerank"):
                decisions = ask_score_batch(states, RERANK_QUESTION, scale="1-5")
        except LayaUnavailable:
            decisions = None

        for pos_in_batch, i in enumerate(to_query):
            deterministic_score, candidate, position = items[i]
            if decisions is None:
                results[i] = (deterministic_score, None)
                continue
            decision = decisions[pos_in_batch]
            normalized = float(decision.answer) if decision.answer is not None else 0.5
            laya_pct = max(0.0, min(1.0, normalized)) * 100.0
            cache_key = _cache_key("rerank", candidate.file_hash, position.id, str(position.jd_version))
            set_cache(cache_key, (laya_pct, decision.raw), settings.CACHE_TTL_DECISION)
            results[i] = _blend(deterministic_score, laya_pct, decision.raw)

    return results


def should_reuse_summary(match: Optional[CandidateMatch], position: Position) -> bool:
    return bool(match and match.llm_summary and match.jd_version == position.jd_version)

