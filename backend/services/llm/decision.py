"""
App-level policy layer that blends an LLM fit score (the DGX Qwen model, see fit_scoring) into TruHire's
deterministic scoring. It only adds a bounded signal on top: when the model is unreachable the
deterministic score is returned unchanged.
"""
import hashlib
from typing import List, Optional, Tuple

from backend.config import settings
from backend.models import Candidate, CandidateMatch, Position
from backend.services.common.ai_audit import ai_feature
<<<<<<< HEAD
from backend.services.llm.laya_service import LayaUnavailable, ask_score_batch

RERANK_QUESTION = "How strong is this candidate's overall fit for this job description?"

=======
from backend.services.common.cache import get_cache, set_cache
from backend.services.llm.fit_scoring import score_fits

RERANK_QUESTION = "How strong is this candidate's overall fit for this job description?"


>>>>>>> 71a313da09018fd7181ca1417fea9d3d5411898b
def _cache_key(*parts: str) -> str:
    digest = hashlib.sha256("||".join(parts).encode("utf-8", "ignore")).hexdigest()
    return f"decision:{digest}"


def _candidate_state(candidate: Candidate, jd_title: str, jd_text: str) -> str:
    return (
        f"{RERANK_QUESTION}\n\n"
        f"Candidate skills: {', '.join(candidate.extracted_skills or [])}\n"
        f"Experience: {candidate.years_experience} years\n"
        f"Education: {candidate.education or 'Not specified'}\n\n"
        f"Job Title: {jd_title}\nJob Description:\n{jd_text[:4000]}"
    )


def _blend(deterministic_score: float, fit_pct: float) -> Tuple[float, dict]:
    blended = ((1 - settings.LAYA_RERANK_WEIGHT) * deterministic_score) + (settings.LAYA_RERANK_WEIGHT * fit_pct)
    return round(blended, 1), {"llm_fit_score": round(fit_pct, 1)}


def rerank_scores_batch(items: List[Tuple[float, Candidate, Position]]) -> List[Tuple[float, Optional[dict]]]:
    """
    Returns (blended_score, fit_signal) per input item, in the same order. Candidates already scored
    for this requirement version are served from the cache; the rest are scored in parallel.
    """
    results: List[Optional[Tuple[float, Optional[dict]]]] = [None] * len(items)
    to_query: List[int] = []
    for i, (deterministic_score, candidate, position) in enumerate(items):
        cached = get_cache(_cache_key("rerank:qwen", candidate.file_hash, position.id, str(position.jd_version)))
        if cached is not None:
            results[i] = _blend(deterministic_score, cached)
        else:
            to_query.append(i)

    if to_query:
        states = [_candidate_state(items[i][1], items[i][2].title, items[i][2].jd_text) for i in to_query]
        with ai_feature("fit_rerank"):
            fits = score_fits(states)
        for i, fit in zip(to_query, fits):
            deterministic_score, candidate, position = items[i]
            if fit is None:
                results[i] = (deterministic_score, None)
                continue
            fit_pct = fit * 100.0
            set_cache(_cache_key("rerank:qwen", candidate.file_hash, position.id, str(position.jd_version)), fit_pct, settings.CACHE_TTL_DECISION)
            results[i] = _blend(deterministic_score, fit_pct)

    return results


def should_reuse_summary(match: Optional[CandidateMatch], position: Position) -> bool:
    return bool(match and match.llm_summary and match.jd_version == position.jd_version)
<<<<<<< HEAD

=======
>>>>>>> 71a313da09018fd7181ca1417fea9d3d5411898b
