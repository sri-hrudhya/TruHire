"""
Safety/groundedness net applied to anything AI-generated that a user sees or that leaves
the system: search narratives, chat replies, JD summaries and candidate emails. Cheap
deterministic checks run first; Laya answers the questions a string check can't, and its
verdicts are cached.

Enforcement (settings.GUARDRAILS_ENFORCE, default on): when Laya can't give a verdict the
text is treated as NOT verified, and callers fall back to their deterministic/heuristic
output or a "please review manually" message. Those "unavailable" outcomes are never
cached, so checks resume the moment Laya is back. Every verdict is written to the AI
audit trail.
"""
import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from backend.config import settings
from backend.services.common import ai_audit
from backend.services.common.ai_audit import ai_feature
from backend.services.common.cache import get_cache, set_cache
from backend.services.llm.laya_service import LayaUnavailable, ask_batch

CHUNK_CHARS = 1000
SOURCE_CHARS = 4000


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


def _chunks(text: str) -> List[str]:
    return [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]


def _unavailable(kind: str) -> Tuple[bool, str]:
    if settings.GUARDRAILS_ENFORCE:
        return False, f"laya_unavailable_{kind}_unverified"
    return True, f"laya_unavailable_assume_{kind}"


def _audit(check: str, result: GuardrailResult, text: str) -> GuardrailResult:
    ai_audit.record(
        provider="guardrail",
        status="ok" if result.passed else "blocked",
        output=text,
        details={"check": check, "for_feature": ai_audit.current_feature(), "grounded": result.grounded,
                 "safe": result.safe, "reason": result.reason, "enforced": settings.GUARDRAILS_ENFORCE},
    )
    return result


def _combine(checks: Iterable[Tuple[bool, str]]) -> Tuple[bool, str]:
    reasons = []
    for ok, reason in checks:
        if not ok:
            return False, reason
        reasons.append(reason)
    return True, reasons[-1] if reasons else "empty"


def check_search_result(cited_quote: str, jd_text: str, summary: str) -> GuardrailResult:
    if not cited_quote and not summary:
        return _audit("search_result", GuardrailResult(True, True, "empty"), "")

    grounding = []
    if cited_quote:
        if cited_quote.strip().lower() in (jd_text or "").lower():
            grounding.append((True, "exact_substring_match"))
        else:
            grounding.append(_laya_groundedness(cited_quote, jd_text))
    # The narrative itself is always checked: a verbatim quote must not vouch for, or an
    # empty quote exempt, an unsupported summary.
    if summary:
        grounding.append(_laya_groundedness(summary, jd_text))
    grounded, grounded_reason = _combine(grounding)
    safe, safe_reason = _laya_safety(summary)
    result = GuardrailResult(grounded, safe, grounded_reason if not grounded else safe_reason)
    return _audit("search_result", result, summary)


def check_chat_reply(reply: str, context: str) -> GuardrailResult:
    grounded, grounded_reason = _laya_groundedness(reply, context)
    safe, safe_reason = _laya_safety(reply)
    result = GuardrailResult(grounded, safe, grounded_reason if not grounded else safe_reason)
    return _audit("chat_reply", result, reply)


def check_decision_reply(reply: str) -> GuardrailResult:
    """
    For a reply that's a judgment/decision statement (e.g. Laya's own direct
    "should I interview this candidate" answer), not a claim extracted from context -
    groundedness doesn't apply (there's no source text a decision needs to match
    verbatim), only the safety/bias check does.
    """
    safe, safe_reason = _laya_safety(reply)
    return _audit("decision_reply", GuardrailResult(True, safe, safe_reason), reply)


def check_generated_text(text: str) -> GuardrailResult:
    """Safety-only check for free-form generated text (e.g. JD summaries)."""
    safe, safe_reason = _laya_safety(text)
    return _audit("generated_text", GuardrailResult(True, safe, safe_reason), text)


URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.I)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def find_unsupported_contacts(text: str, allowed_sources: str) -> List[str]:
    """URLs, email addresses and phone numbers in `text` that don't appear in `allowed_sources`.

    Outbound email must never carry a link or contact detail the recruiter didn't supply:
    that is exactly what an injected instruction ("ask them to confirm bank details at
    http://...") would add.
    """
    allowed = (allowed_sources or "").lower()
    allowed_digits = _digits(allowed)
    found = []
    for match in URL_PATTERN.findall(text) + EMAIL_PATTERN.findall(text):
        token = match.rstrip(".,;:").lower()
        if token not in allowed:
            found.append(token)
    for match in PHONE_PATTERN.findall(text):
        digits = _digits(match)
        if len(digits) >= 8 and digits not in allowed_digits:
            found.append(match.strip())
    return found


def check_email_draft(subject: str, body: str, allowed_sources: str) -> GuardrailResult:
    text = f"{subject}\n\n{body}"
    unsupported = find_unsupported_contacts(text, allowed_sources)
    if unsupported:
        result = GuardrailResult(False, True, "unsupported_link_or_contact: " + ", ".join(unsupported[:5]))
        return _audit("email_draft", result, text)
    safe, safe_reason = _laya_safety(text)
    return _audit("email_draft", GuardrailResult(True, safe, safe_reason), text)


def _laya_groundedness(claim: str, source_text: str) -> Tuple[bool, str]:
    if not claim:
        return True, "no_claim_to_check"
    source = (source_text or "")[:SOURCE_CHARS]
    for chunk in _chunks(claim):
        ok, reason = _grounded_chunk(chunk, source)
        if not ok:
            return ok, reason
    return True, "laya_groundedness_check"


def _grounded_chunk(chunk: str, source: str) -> Tuple[bool, str]:
    key = _cache_key("grounded", chunk, source[:2000])
    cached = get_cache(key)
    if cached is not None:
        return tuple(cached)
    try:
        with ai_feature("guardrail"):
            decision = ask_batch(
                f"Source text:\n{source}\n\nClaim:\n{chunk}",
                [{"id": "q", "type": "noul", "question": "Is the claim a faithful, non-hallucinated statement grounded in the source text?"}],
            )[0]
    except LayaUnavailable:
        return _unavailable("grounded")
    result = (bool(decision.answer) or decision.probability >= 0.5, "laya_groundedness_check")
    set_cache(key, result, settings.CACHE_TTL_DECISION)
    return result


def _laya_safety(text: str) -> Tuple[bool, str]:
    if not text:
        return True, "empty_text"
    for chunk in _chunks(text):
        ok, reason = _safe_chunk(chunk)
        if not ok:
            return ok, reason
    return True, "laya_safety_check"


def _safe_chunk(chunk: str) -> Tuple[bool, str]:
    key = _cache_key("safety", chunk)
    cached = get_cache(key)
    if cached is not None:
        return tuple(cached)
    try:
        with ai_feature("guardrail"):
            decision = ask_batch(
                chunk,
                [{"id": "q", "type": "noul", "question": "Does this text contain unsafe, biased, or discriminatory language about a candidate?"}],
            )[0]
    except LayaUnavailable:
        return _unavailable("safe")
    is_unsafe = bool(decision.answer) and decision.probability >= 0.5
    result = (not is_unsafe, "laya_safety_check")
    set_cache(key, result, settings.CACHE_TTL_DECISION)
    return result
