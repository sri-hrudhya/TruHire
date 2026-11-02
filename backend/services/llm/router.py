"""
LLM chat router: DGX/vLLM first, then the cloud providers.

Order:  vLLM (DGX Qwen)  ->  OpenRouter  ->  Groq  ->  Gemini
Each cloud provider tries all of its API keys (see providers/_openai_compat.py) before the next
provider is used. The whole call is capped by LLM_TOTAL_TIMEOUT.

Fallback is triggered only by infrastructure failures (cannot connect, timeout, HTTP 5xx/429),
signalled with ``TransientLLMError``. Application-level vLLM errors (bad request, bad JSON,
"no choices") propagate unchanged because every provider would fail the same way.

A small circuit breaker stops paying the DGX connect/read wait on every request while it is down:
after LLM_VLLM_BREAKER_FAILURES consecutive failures vLLM is skipped for LLM_VLLM_BREAKER_COOLDOWN
seconds, then probed again by the next request. When the DGX answers, it is first in line again.

Text sent to a cloud provider is PII-redacted first (LLM_CLOUD_REDACT_PII).
Embeddings are not routed here; they use local_embeddings.py.

chat_completion returns the whole reply; chat_completion_stream yields it in pieces as it is written.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional

import httpx

from backend.config import settings
from backend.services.common import ai_audit
from backend.services.ingestion.pii import redact_pii
from backend.services.llm import vllm as _vllm
from backend.services.llm.errors import TransientLLMError
from backend.services.llm.providers._openai_compat import CloudProvider

logger = logging.getLogger(__name__)

_breaker_lock = threading.Lock()
_vllm_failures = 0
_vllm_skip_until = 0.0


def _vllm_available() -> bool:
    with _breaker_lock:
        return time.monotonic() >= _vllm_skip_until


def _vllm_succeeded() -> None:
    global _vllm_failures, _vllm_skip_until
    with _breaker_lock:
        _vllm_failures = 0
        _vllm_skip_until = 0.0


def _vllm_failed() -> None:
    global _vllm_failures, _vllm_skip_until
    with _breaker_lock:
        _vllm_failures += 1
        if _vllm_failures >= settings.LLM_VLLM_BREAKER_FAILURES:
            _vllm_skip_until = time.monotonic() + settings.LLM_VLLM_BREAKER_COOLDOWN
            logger.warning("vLLM failed %d times in a row; using cloud providers for %.0fs.",
                           _vllm_failures, settings.LLM_VLLM_BREAKER_COOLDOWN)


@dataclass
class _CloudPlan:
    """What a cloud fallback needs: providers with keys, the redacted messages, and the audit prompt."""
    providers: List[CloudProvider]
    messages: List[Dict[str, str]]
    prompt_text: str


def _plan_cloud(messages: List[Dict[str, str]], last_exc: Exception) -> _CloudPlan:
    from backend.services.llm.providers.cloud import CHAIN

    providers = [p for p in CHAIN if p.keys()]
    if not providers:
        raise TransientLLMError(
            "vLLM (DGX) is unavailable and no cloud provider keys are configured. "
            "Set OPENROUTER_API_KEY_1, GROQ_API_KEY_1 or GEMINI_API_KEY_1 in .env."
        ) from last_exc
    safe = messages if not settings.LLM_CLOUD_REDACT_PII else [{**m, "content": redact_pii(m.get("content") or "")} for m in messages]
    return _CloudPlan(providers, safe, "\n\n".join(f"[{m.get('role')}] {m.get('content') or ''}" for m in safe))


def _audit_cloud(provider: CloudProvider, plan: _CloudPlan, started: float, *, output: Optional[str], error: Optional[str] = None, streamed: bool = False) -> None:
    ai_audit.record(
        provider=provider.name, model=provider.model_name(), status="error" if error else "ok", prompt=plan.prompt_text,
        output=output or None, latency_ms=(time.perf_counter() - started) * 1000, error=error,
        details=None if error else {"fallback": True, "streamed": streamed, "pii_redacted": settings.LLM_CLOUD_REDACT_PII},
    )


def _vllm_timeout() -> httpx.Timeout:
    wait = min(settings.LLM_VLLM_CHAT_TIMEOUT, settings.LLM_TOTAL_TIMEOUT)
    return httpx.Timeout(wait, connect=min(settings.LLM_CONNECT_TIMEOUT, wait))


def _all_failed(last_exc: Exception) -> TransientLLMError:
    return TransientLLMError(f"All LLM providers failed. Last error: {last_exc}. Check DGX connectivity and cloud API keys/quotas.")


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    enable_thinking: bool = True,
) -> str:
    """Chat completion through the vLLM -> OpenRouter -> Groq -> Gemini chain (see module docstring)."""
    deadline = time.monotonic() + settings.LLM_TOTAL_TIMEOUT
    last_exc: Exception = TransientLLMError("No LLM provider is available.")

    if _vllm_available():
        try:
            result = _vllm.chat_completion(messages, temperature=temperature, max_tokens=max_tokens,
                                           enable_thinking=enable_thinking, timeout=_vllm_timeout())
            _vllm_succeeded()
            return result
        except TransientLLMError as exc:
            _vllm_failed()
            last_exc = exc
            logger.warning("vLLM unavailable (%s); switching to cloud providers.", str(exc).splitlines()[0])
    else:
        logger.info("vLLM skipped (circuit open); using cloud providers.")

    plan = _plan_cloud(messages, last_exc)
    for provider in plan.providers:
        started = time.perf_counter()
        try:
            logger.info("Trying cloud provider: %s", provider.name)
            result = provider.chat_completion(plan.messages, temperature=temperature, max_tokens=max_tokens, deadline=deadline)
        except RuntimeError as exc:  # TransientLLMError is a RuntimeError; a hard error on one provider still tries the next
            _audit_cloud(provider, plan, started, output=None, error=str(exc)[:500])
            logger.warning("Provider %s failed (%s); trying next.", provider.name, str(exc)[:200])
            last_exc = exc
            if time.monotonic() >= deadline:
                break
            continue
        _audit_cloud(provider, plan, started, output=result)
        return result
    raise _all_failed(last_exc) from last_exc


def chat_completion_stream(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    enable_thinking: bool = True,
) -> Iterator[str]:
    """Streaming chat_completion: yields the reply in pieces as soon as the first provider starts answering.

    Same order, circuit breaker, key rotation and PII redaction as chat_completion. Failing over is only
    possible before the first piece: once text has reached the caller, a failure ends the stream with an
    error instead of restarting the answer on another provider."""
    deadline = time.monotonic() + settings.LLM_TOTAL_TIMEOUT
    last_exc: Exception = TransientLLMError("No LLM provider is available.")
    delivered = False

    if _vllm_available():
        try:
            for piece in _vllm.chat_completion_stream(messages, temperature=temperature, max_tokens=max_tokens,
                                                      enable_thinking=enable_thinking, timeout=_vllm_timeout()):
                delivered = True
                yield piece
            _vllm_succeeded()
            return
        except TransientLLMError as exc:
            if delivered:
                raise RuntimeError("The answer was interrupted; please ask again.") from exc
            _vllm_failed()
            last_exc = exc
            logger.warning("vLLM unavailable (%s); switching to cloud providers.", str(exc).splitlines()[0])
    else:
        logger.info("vLLM skipped (circuit open); using cloud providers.")

    plan = _plan_cloud(messages, last_exc)
    for provider in plan.providers:
        started = time.perf_counter()
        parts: List[str] = []
        try:
            logger.info("Trying cloud provider (streaming): %s", provider.name)
            for piece in provider.chat_completion_stream(plan.messages, temperature=temperature, max_tokens=max_tokens, deadline=deadline):
                parts.append(piece)
                yield piece
        except RuntimeError as exc:
            _audit_cloud(provider, plan, started, output="".join(parts), error=str(exc)[:500], streamed=True)
            if parts:
                raise  # half-delivered: cannot restart elsewhere
            logger.warning("Provider %s failed (%s); trying next.", provider.name, str(exc)[:200])
            last_exc = exc
            if time.monotonic() >= deadline:
                break
            continue
        _audit_cloud(provider, plan, started, output="".join(parts), streamed=True)
        return
    raise _all_failed(last_exc) from last_exc
