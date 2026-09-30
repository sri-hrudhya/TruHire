"""
App-level policy layer on top of laya_service: composes Laya's fast typed decisions with
TruHire's existing deterministic scoring, and decides when a question is cheap enough for
Laya alone versus when it must escalate to the vLLM LLM path. Nothing here changes the
existing deterministic formulas in scoring.py/ai_service.py — Laya only adds a bounded
signal on top, or is skipped entirely (falling back to today's behavior) when unavailable
or unconfident.
"""
import hashlib
from typing import List, Literal, Optional, Tuple

from backend.config import settings
from backend.models import Candidate, CandidateMatch, Position
from backend.services.common.cache import get_cache, set_cache
from backend.services.llm.laya_service import LayaDecision, LayaUnavailable, ask_choice, ask_score, ask_score_batch, ask_yesno

RERANK_QUESTION = "How strong is this candidate's overall fit for this job description?"

ChatIntent = Literal["open_qa", "interview_decision", "compare_candidates"]


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


def rerank_score(deterministic_score: float, candidate: Candidate, position: Position) -> Tuple[float, Optional[dict]]:
    """
    Blends the existing deterministic hybrid score (0-100) with a fast Laya fit
    judgment. Falls back to the deterministic score unchanged if Laya is unavailable.
    Single-candidate convenience wrapper; prefer rerank_scores_batch for a whole pool -
    one call per candidate measured ~0.4s on CPU (no GPU here), so scoring a full
    retrieval pool one-by-one adds tens of seconds to a single search.
    """
    cache_key = _cache_key("rerank", candidate.file_hash, position.id, str(position.jd_version))
    cached = get_cache(cache_key)
    if cached is not None:
        laya_pct, raw = cached
    else:
        try:
            decision = ask_score(
                _candidate_state(candidate, position.title, position.jd_text),
                RERANK_QUESTION,
                scale="1-5",
            )
            # decision.answer is already normalized to [0, 1] by laya_service._to_decision.
            normalized = float(decision.answer) if decision.answer is not None else 0.5
            laya_pct = max(0.0, min(1.0, normalized)) * 100.0
            raw = decision.raw
        except LayaUnavailable:
            return deterministic_score, None
        set_cache(cache_key, (laya_pct, raw), settings.CACHE_TTL_DECISION)

    return _blend(deterministic_score, laya_pct, raw)


def rerank_scores_batch(items: List[Tuple[float, Candidate, Position]]) -> List[Tuple[float, Optional[dict]]]:
    """
    Batched form of rerank_score: one shared Laya forward pass for every candidate in
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


def classify_chat_intent(latest_message: str) -> ChatIntent:
    try:
        decision = ask_choice(
            latest_message[:1000],
            "What kind of request is this?",
            options=["open_qa", "interview_decision", "compare_candidates"],
            criteria="interview_decision = asking whether to interview/hire one candidate. "
                     "compare_candidates = asking to compare or rank multiple candidates. "
                     "open_qa = anything else, including general questions about a candidate or JD.",
        )
        if decision.should_escalate or decision.answer not in ("open_qa", "interview_decision", "compare_candidates"):
            return "open_qa"
        return decision.answer
    except LayaUnavailable:
        return "open_qa"


def decide_interview(candidate_context: str, jd_context: str) -> LayaDecision:
    return ask_yesno(
        f"{candidate_context}\n\n{jd_context}",
        "Should this candidate be interviewed for this role?",
        criteria="Base the decision on skill overlap, experience, and education fit shown above.",
    )


MAX_COMPARE_CANDIDATES = 6  # Laya's max_prefixes limit


def decide_compare(candidate_names: List[str], candidates_context: List[str], jd_context: str) -> LayaDecision:
    if len(candidate_names) > MAX_COMPARE_CANDIDATES:
        raise LayaUnavailable(f"Too many candidates ({len(candidate_names)}) for Laya's choice head; escalate to LLM.")
    state = jd_context + "\n\n" + "\n\n".join(candidates_context)
    return ask_choice(
        state,
        "Which candidate is the strongest fit for this role?",
        options=candidate_names,
    )
