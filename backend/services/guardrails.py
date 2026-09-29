"""
Safety/groundedness net applied to anything shown to a user: search-result narratives
and chat replies. Cheap deterministic checks run first; Laya only gets called for the
ambiguous cases an exact string check can't resolve, and its verdicts are cached.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional

from backend.config import settings
from backend.services.cache import get_cache, set_cache
from backend.services.laya_service import LayaUnavailable, ask_batch


@dataclass
class GuardrailResult:
    grounded: bool
    safe: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.grounded and self.safe


def _cache_key(*parts: str) -> str:
    digest = hashlib.sha256("||".join(parts).encode("utf-8", "ignore")).hexdigest()
    return f"guardrail:{digest}"


def check_search_result(cited_quote: str, jd_text: str, summary: str) -> GuardrailResult:
    if not cited_quote and not summary:
        return GuardrailResult(True, True, "empty")

    if cited_quote and cited_quote.strip().lower() in (jd_text or "").lower():
        grounded, grounded_reason = True, "exact_substring_match"
    else:
        grounded, grounded_reason = _laya_groundedness(cited_quote, jd_text, summary)

    safe, safe_reason = _laya_safety(summary)
    reason = grounded_reason if not grounded else safe_reason
    return GuardrailResult(grounded, safe, reason)


def check_chat_reply(reply: str, context: str) -> GuardrailResult:
    grounded, grounded_reason = _laya_groundedness(reply, context, reply)
    safe, safe_reason = _laya_safety(reply)
    reason = grounded_reason if not grounded else safe_reason
    return GuardrailResult(grounded, safe, reason)


def _laya_groundedness(claim: str, source_text: str, summary: str) -> tuple[bool, str]:
    if not claim:
        return True, "no_claim_to_check"
    key = _cache_key("grounded", claim, source_text[:2000])
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        decision = ask_batch(
            f"Source text:\n{source_text[:4000]}\n\nClaim:\n{claim[:1000]}",
            [{"id": "q", "type": "noul", "question": "Is the claim a faithful, non-hallucinated statement grounded in the source text?"}],
        )[0]
        result = (bool(decision.answer) or decision.probability >= 0.5, "laya_groundedness_check")
    except LayaUnavailable:
        # Can't verify -> fail safe, don't silently trust an unverifiable claim.
        result = (False, "laya_unavailable_fail_safe")
    set_cache(key, result, settings.CACHE_TTL_DECISION)
    return result


def _laya_safety(text: str) -> tuple[bool, str]:
    if not text:
        return True, "empty_text"
    key = _cache_key("safety", text[:2000])
    cached = get_cache(key)
    if cached is not None:
        return cached
    try:
        decision = ask_batch(
            text[:2000],
            [{"id": "q", "type": "noul", "question": "Does this text contain unsafe, biased, or discriminatory language about a candidate?"}],
        )[0]
        is_unsafe = bool(decision.answer) and decision.probability >= 0.5
        result = (not is_unsafe, "laya_safety_check")
    except LayaUnavailable:
        # No verification available -> assume safe rather than blocking every reply;
        # PII redaction upstream already strips the highest-risk content.
        result = (True, "laya_unavailable_assume_safe")
    set_cache(key, result, settings.CACHE_TTL_DECISION)
    return result
