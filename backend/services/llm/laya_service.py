"""
Thin wrapper around the local `laya` decision model (convaiinnovations/laya).

Laya is a non-autoregressive encoder that answers typed choice/score/noul (yes-no)
questions with calibrated probabilities in a single forward pass, instead of an LLM
chat-completion round trip. It also emits its own confidence, which callers use to
decide whether to escalate to the vLLM LLM path.

If `laya`/`torch` aren't installed or LAYA_ENABLED is false, every function here raises
LayaUnavailable, and callers are expected to treat that exactly like "should_escalate".

Everything below this module's public functions uses an app-level question shape
({"id", "type", "question", "options"?, "criteria"?}) that's stable regardless of the
installed `laya` package's own schema - `_to_laya_question`/`_to_decision` are the only
places that need to change if that schema changes again.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.config import settings

_router = None
_load_attempted = False

# Real laya package "score" questions take `criteria` as an ordered list of level
# descriptions (index 0 = lowest); this is the only scale currently used.
_SCORE_LEVELS = {
    "1-5": ["very poor fit", "weak fit", "moderate fit", "strong fit", "excellent fit"],
}


class LayaUnavailable(Exception):
    pass


@dataclass
class LayaDecision:
    answer: Any
    probability: float
    should_escalate: bool
    raw: Dict[str, Any]


import os
import warnings

# Suppress Hugging Face symlinks warning on Windows and temperature calibration warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", message=".*laya: this checkpoint ships invalid temperatures.*")


def _find_local_laya_dir() -> Optional[str]:
    """Finds existing local snapshot directory for convaiinnovations/laya."""
    custom_path = getattr(settings, "LAYA_MODEL_PATH", None)
    if custom_path and os.path.exists(custom_path):
        return custom_path

    hf_cache = os.path.expanduser("~/.cache/huggingface/hub/models--convaiinnovations--laya/snapshots")
    if os.path.exists(hf_cache):
        snapshots = [
            os.path.join(hf_cache, s)
            for s in os.listdir(hf_cache)
            if os.path.isdir(os.path.join(hf_cache, s))
        ]
        # Sort by modification time to get the most recent snapshot
        snapshots.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for snap_dir in snapshots:
            if os.path.isfile(os.path.join(snap_dir, "model.safetensors")):
                return snap_dir
    return None


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

        local_dir = _find_local_laya_dir()
        if local_dir:
            # Checkpoint is already downloaded on disk; enforce offline mode
            os.environ["HF_HUB_OFFLINE"] = "1"
            print(f"[laya] Using local checkpoint at {local_dir} (zero network downloads)")
            models = {
                "english": (local_dir, None),
                "multilingual": (local_dir, "multilingual"),
                "typed-decisions": (local_dir, "typed-decisions"),
            }
            # max_loaded=3 ensures models remain cached in memory and are not evicted/reloaded
            _router = Router(models=models, max_loaded=3, preload=False)
        else:
            # Fallback if no local snapshot exists yet
            _router = Router(max_loaded=3, preload=False)
    except Exception as exc:
        raise LayaUnavailable(f"Laya could not be loaded: {exc}") from exc
    return _router


def _to_laya_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """Translate our app-level question shape into laya's real per-question schema:
    {"type", "instructions", "criteria"?}. See laya.agent.Agent._check_question for the
    authoritative shape (verified against the installed package, not the model card)."""
    instructions = q["question"]
    if q.get("criteria"):
        instructions = f"{instructions} ({q['criteria']})"

    qtype = q["type"]
    if qtype == "choice":
        return {"type": "choice", "instructions": instructions, "criteria": list(q["options"])}
    if qtype == "score":
        levels = _SCORE_LEVELS.get(q.get("scale", "1-5"), _SCORE_LEVELS["1-5"])
        return {"type": "score", "instructions": instructions, "criteria": levels}
    # noul: real "criteria" (if set) must be keyed only "true"/"false" - our free-text
    # guidance already went into instructions above, so omit it here.
    return {"type": "noul", "instructions": instructions}


def _to_decision(raw_answer: Dict[str, Any]) -> LayaDecision:
    qtype = raw_answer.get("type")
    if qtype == "choice":
        answer = raw_answer.get("choice")
        probability = float((raw_answer.get("probabilities") or {}).get(answer, 0.0))
    elif qtype == "score":
        # Expected value over ordered levels (0..len(levels)-1), normalized to [0, 1].
        levels = raw_answer.get("legend") or {}
        max_index = max((int(k) for k in levels.keys()), default=0) or 1
        answer = float(raw_answer.get("score", 0.0)) / max_index
        probability = float(raw_answer.get("confidence", 0.0))
    elif qtype == "noul":
        probability = float(raw_answer.get("noul", 0.0))
        answer = probability >= 0.5
    else:
        answer, probability = None, 0.0

    confidence = float(raw_answer.get("answer_confidence", raw_answer.get("confidence", 0.0)))
    return LayaDecision(
        answer=answer,
        probability=probability,
        should_escalate=confidence < settings.LAYA_CONFIDENCE_THRESHOLD,
        raw=raw_answer,
    )


def ask_batch(state: str, questions: List[Dict[str, Any]]) -> List[LayaDecision]:
    """
    questions: list of {"id": str, "type": "choice"|"score"|"noul", "question": str,
    "options": [...] (choice only), "criteria": str (optional guidance), "scale": str
    (score only, default "1-5")}.
    """
    router = _get_router()
    laya_questions = {q["id"]: _to_laya_question(q) for q in questions}
    try:
        result = router.predict(state, laya_questions)
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
    q = {"id": "q", "type": "score", "question": question, "scale": scale}
    return ask_batch(state, [q])[0]


def ask_score_batch(states: List[str], question: str, scale: str = "1-5") -> List[LayaDecision]:
    """
    Like ask_score, but for many states against the SAME question in one shared
    forward pass via Router.predict_batch - critical for latency: a plain Python loop
    calling ask_score once per candidate measured ~0.4s/call on CPU, which is ~40s for
    a single 100-candidate JD search. Batching amortizes the fixed per-call overhead
    across the whole pool in one shot.
    """
    if not states:
        return []
    router = _get_router()
    laya_question = _to_laya_question({"id": "q", "type": "score", "question": question, "scale": scale})
    requests = [{"state": state, "questions": {"q": laya_question}} for state in states]
    try:
        results = router.predict_batch(requests)
    except Exception as exc:
        raise LayaUnavailable(f"Laya batch inference failed: {exc}") from exc
    return [_to_decision((result.get("answers") or {}).get("q", {})) for result in results]
