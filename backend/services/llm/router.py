"""
LLM chat router — provider fallback chain for chat completions only.

Priority order:
  1. vLLM       (DGX self-hosted — primary, most powerful)
  2. OpenRouter  (cloud — 1st fallback)
  3. Groq        (cloud — 2nd fallback, ultra-fast inference)
  4. Gemini      (cloud — 3rd fallback, 3 API keys for high rate-limit headroom)

Embeddings are NOT routed here; they use local_embeddings.py via ai_service.py
and are completely unaffected by this module.

Fallback is triggered ONLY on infrastructure failures:
  - Connection errors (DGX/provider unreachable)
  - Timeouts
  - 5xx server errors

Application-level errors (bad JSON from a working server, guardrail failures,
"no choices" from a responsive endpoint) are NOT retried — they propagate
immediately because they would fail the same way on every provider.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

from backend.services.llm import vllm as _vllm

logger = logging.getLogger(__name__)

# Substrings in the RuntimeError message that indicate a transient infra failure
# (worth trying the next provider). Must be lowercase for comparison.
_TRANSIENT_MARKERS = (
    "could not connect",
    "timed out",
    "unreachable",
    "server error",
    " 502",
    " 503",
    " 504",
    "connection",
)


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def _configured_fallbacks() -> List[Tuple[str, Callable]]:
    """
    Build the ordered list of cloud fallback providers from whatever keys are
    present in .env. Providers with no keys configured are skipped silently.
    Imports are deferred so missing config doesn't break startup.
    """
    from backend.config import settings

    fallbacks: List[Tuple[str, Callable]] = []

    if settings.OPENROUTER_API_KEY_1 or settings.OPENROUTER_API_KEY_2:
        from backend.services.llm.providers.openrouter import (
            chat_completion as _or_chat,
        )
        fallbacks.append(("openrouter", _or_chat))

    if settings.GROQ_API_KEY_1 or settings.GROQ_API_KEY_2:
        from backend.services.llm.providers.groq import chat_completion as _groq_chat
        fallbacks.append(("groq", _groq_chat))

    if any(
        [settings.GEMINI_API_KEY_1, settings.GEMINI_API_KEY_2, settings.GEMINI_API_KEY_3]
    ):
        from backend.services.llm.providers.gemini import (
            chat_completion as _gemini_chat,
        )
        fallbacks.append(("gemini", _gemini_chat))

    return fallbacks


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    enable_thinking: bool = True,
) -> str:
    """
    Send a chat completion request through the provider fallback chain.

    The ``enable_thinking`` flag is vLLM/Qwen-specific (controls chain-of-thought
    generation) and is silently ignored by cloud fallback providers.
    """
    # ── 1. Primary: vLLM (DGX) ──────────────────────────────────────────────
    try:
        return _vllm.chat_completion(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
        )
    except RuntimeError as exc:
        if not _is_transient(exc):
            raise  # Application-level error — don't mask it with a fallback
        logger.warning("vLLM unavailable (%s) — activating cloud fallback chain.", exc)

    # ── 2–4. Cloud fallbacks: OpenRouter → Groq → Gemini ────────────────────
    fallbacks = _configured_fallbacks()
    if not fallbacks:
        raise RuntimeError(
            "vLLM (DGX) is unreachable and no cloud fallback providers are configured. "
            "Set at least one of: OPENROUTER_API_KEY_1, GROQ_API_KEY_1, GEMINI_API_KEY_1 in .env."
        )

    last_exc: Exception = RuntimeError("All LLM providers failed.")
    for name, fn in fallbacks:
        try:
            logger.info("Trying fallback provider: %s", name)
            result = fn(messages, temperature=temperature, max_tokens=max_tokens)
            logger.info("Fallback provider %s succeeded.", name)
            return result
        except RuntimeError as exc:
            if _is_transient(exc):
                logger.warning(
                    "Provider %s unavailable (%s), trying next fallback.", name, exc
                )
                last_exc = exc
                continue
            raise  # Non-transient error (e.g. all keys rate-limited) — propagate now

    raise RuntimeError(
        f"All LLM providers exhausted. Last error: {last_exc}. "
        "Check DGX connectivity, and OpenRouter / Groq / Gemini API keys and quotas."
    ) from last_exc
