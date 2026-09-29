"""
Thin wrapper around the local `laya` decision model (convaiinnovations/laya).

Laya is a non-autoregressive encoder that answers typed choice/score/noul (yes-no)
questions with calibrated probabilities in a single forward pass, instead of an LLM
chat-completion round trip. It also emits its own confidence, which callers use to
decide whether to escalate to the vLLM LLM path.

If `laya`/`torch` aren't installed or LAYA_ENABLED is false, every function here raises
LayaUnavailable, and callers are expected to treat that exactly like "should_escalate".
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.config import settings

_router = None
_load_attempted = False


class LayaUnavailable(Exception):
    pass


@dataclass
class LayaDecision:
    answer: Any
    probability: float
    should_escalate: bool
    raw: Dict[str, Any]


def _get_router():
    global _router, _load_attempted
    if _router is not None:
        return _router
    if not settings.LAYA_ENABLED:
        raise LayaUnavailable("Laya is disabled (LAYA_ENABLED=false).")
    if _load_attempted:
        raise LayaUnavailable("Laya failed to load on a previous attempt.")
    _load_attempted = True
    try:
        from laya import Router
        _router = Router(preload=True)
    except Exception as exc:
        raise LayaUnavailable(f"Laya could not be loaded: {exc}") from exc
    return _router


def _to_decision(raw_answer: Dict[str, Any]) -> LayaDecision:
    probability = float(raw_answer.get("probability", raw_answer.get("confidence", 0.0)))
    return LayaDecision(
        answer=raw_answer.get("answer"),
        probability=probability,
        should_escalate=bool(raw_answer.get("escalate")) or probability < settings.LAYA_CONFIDENCE_THRESHOLD,
        raw=raw_answer,
    )


def ask_batch(state: str, questions: List[Dict[str, Any]]) -> List[LayaDecision]:
    """
    questions: list of {"id": str, "type": "choice"|"score"|"noul", "question": str,
    "options": [...] (choice only), "criteria": str (optional)}
    """
    router = _get_router()
    try:
        result = router.predict(state, questions)
    except Exception as exc:
        raise LayaUnavailable(f"Laya inference failed: {exc}") from exc
    answers = result.get("answers", {})
    return [_to_decision(answers.get(q["id"], {})) for q in questions]


def ask_choice(state: str, question: str, options: List[str], criteria: str = "") -> LayaDecision:
    q = {"id": "q", "type": "choice", "question": question, "options": options, "criteria": criteria}
    return ask_batch(state, [q])[0]


def ask_yesno(state: str, question: str, criteria: str = "") -> LayaDecision:
    q = {"id": "q", "type": "noul", "question": question, "criteria": criteria}
    return ask_batch(state, [q])[0]


def ask_score(state: str, question: str, scale: str = "1-5") -> LayaDecision:
    q = {"id": "q", "type": "score", "question": question, "criteria": f"scale:{scale}"}
    return ask_batch(state, [q])[0]
