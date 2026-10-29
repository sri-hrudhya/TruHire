"""Candidate-vs-JD fit scoring on the DGX Qwen model, one short request per candidate, run in parallel."""
import contextvars
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from backend.config import settings
from backend.services.llm import vllm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You rate how well a candidate fits a job description. "
    "Reply with a single digit from 1 (very poor fit) to 5 (excellent fit) and nothing else."
)
_DIGIT = re.compile(r"[1-5]")


def _score_one(state: str, down: threading.Event) -> Optional[float]:
    """Fit in [0, 1], or None when the model is unreachable or answers with no 1-5 digit."""
    if down.is_set():
        return None
    try:
        reply = vllm.chat_completion(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": state}],
            temperature=0.0, max_tokens=4, enable_thinking=False,
        )
    except Exception as exc:
        down.set()
        logger.warning("fit scoring unavailable, skipping the rerank for this search: %s", exc)
        return None
    match = _DIGIT.search(reply)
    return (int(match.group()) - 1) / 4 if match else None


def score_fits(states: List[str]) -> List[Optional[float]]:
    """One score per state, same order. The first failed request stops the rest of the batch."""
    if not states:
        return []
    down = threading.Event()
    with ThreadPoolExecutor(max_workers=max(1, settings.FIT_SCORE_WORKERS)) as pool:
        # Each task runs in a copy of the caller's context so audit events keep their user, trace and feature.
        futures = [pool.submit(contextvars.copy_context().run, _score_one, state, down) for state in states]
        return [f.result() for f in futures]
