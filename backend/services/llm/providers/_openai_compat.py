"""Shared OpenAI-compatible chat call with API-key rotation for the cloud fallback providers.

Every configured key is tried before the provider is given up on: a timeout, connection error,
HTTP 429/401/403/5xx on one key moves on to the next key. Keys that just failed go on a short
cooldown so the next request does not wait on them again, and the first key tried rotates
round-robin so load is spread across keys.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from backend.config import settings
from backend.services.llm.errors import TransientLLMError
from backend.services.llm.streaming import iter_text_deltas

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_next_start: Dict[str, int] = {}
_cooldown_until: Dict[str, float] = {}  # "<provider>:<key tail>" -> monotonic time


def _key_id(provider: str, key: str) -> str:
    return f"{provider}:{key[-6:]}"


def _ordered_keys(provider: str, keys: List[str]) -> List[str]:
    """Round-robin start, healthy keys first; cooling-down keys are still kept as a last resort."""
    with _lock:
        start = _next_start.get(provider, 0) % len(keys)
        _next_start[provider] = start + 1
        now = time.monotonic()
        rotated = keys[start:] + keys[:start]
        healthy = [k for k in rotated if _cooldown_until.get(_key_id(provider, k), 0) <= now]
        cooling = [k for k in rotated if k not in healthy]
        return healthy + cooling


def _cool_down(provider: str, key: str, seconds: float) -> None:
    with _lock:
        _cooldown_until[_key_id(provider, key)] = time.monotonic() + seconds


def chat_with_keys(
    provider: str,
    endpoint: str,
    keys: List[str],
    payload: Dict[str, Any],
    *,
    deadline: Optional[float] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """POST the chat payload, rotating through ``keys``. ``deadline`` is a ``time.monotonic()`` instant."""
    if not keys:
        raise TransientLLMError(f"{provider}: no API keys configured.")

    last_err = f"{provider}: unknown error."
    for key in _ordered_keys(provider, keys):
        per_key = settings.LLM_CLOUD_KEY_TIMEOUT
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise TransientLLMError(f"{provider}: overall time budget used up. Last error: {last_err}")
            per_key = min(per_key, remaining)
        timeout = httpx.Timeout(per_key, connect=min(settings.LLM_CONNECT_TIMEOUT, per_key))
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra_headers or {})}
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
        except httpx.TimeoutException:
            last_err = f"{provider} key ...{key[-4:]} timed out after {per_key:.0f}s"
            _cool_down(provider, key, settings.LLM_KEY_COOLDOWN_SECONDS)
            logger.warning("%s; trying next key/provider.", last_err)
            continue
        except httpx.HTTPError as exc:
            last_err = f"{provider} key ...{key[-4:]} connection error: {type(exc).__name__}"
            _cool_down(provider, key, settings.LLM_KEY_COOLDOWN_SECONDS)
            logger.warning("%s; trying next key/provider.", last_err)
            continue

        code = resp.status_code
        if code in (401, 403) or code == 429 or code >= 500:
            last_err = f"{provider} key ...{key[-4:]} returned HTTP {code}"
            _cool_down(provider, key, 600 if code in (401, 403) else settings.LLM_KEY_COOLDOWN_SECONDS)
            logger.warning("%s; trying next key/provider.", last_err)
            continue
        if code >= 400:
            # Bad request / unknown model: identical on every key, so stop rotating.
            raise RuntimeError(f"{provider} {code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"{provider} returned invalid JSON: {resp.text[:300]}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{provider} returned no choices.")
        content = (choices[0].get("message") or {}).get("content")
        return "" if content is None else str(content)

    raise TransientLLMError(f"{provider}: all {len(keys)} key(s) failed. Last error: {last_err}")


def stream_with_keys(
    provider: str,
    endpoint: str,
    keys: List[str],
    payload: Dict[str, Any],
    *,
    deadline: Optional[float] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Iterator[str]:
    """Streaming twin of chat_with_keys: yields reply pieces as they arrive.

    Keys rotate exactly as in chat_with_keys until the first piece arrives; the timeout is the wait for
    each piece, so a key that connects but never answers is skipped after LLM_CLOUD_KEY_TIMEOUT. Once a
    piece has been yielded the reply is committed to that key, and a later failure ends the stream with
    a plain RuntimeError (the router must not restart a half-delivered answer elsewhere)."""
    if not keys:
        raise TransientLLMError(f"{provider}: no API keys configured.")
    payload = {**payload, "stream": True}

    last_err = f"{provider}: unknown error."
    for key in _ordered_keys(provider, keys):
        per_key = settings.LLM_CLOUD_KEY_TIMEOUT
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise TransientLLMError(f"{provider}: overall time budget used up. Last error: {last_err}")
            per_key = min(per_key, remaining)
        timeout = httpx.Timeout(per_key, connect=min(settings.LLM_CONNECT_TIMEOUT, per_key))
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra_headers or {})}
        started_yielding = False
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", endpoint, headers=headers, json=payload) as resp:
                    code = resp.status_code
                    if code in (401, 403, 429) or code >= 500:
                        last_err = f"{provider} key ...{key[-4:]} returned HTTP {code}"
                        _cool_down(provider, key, 600 if code in (401, 403) else settings.LLM_KEY_COOLDOWN_SECONDS)
                        logger.warning("%s; trying next key/provider.", last_err)
                        continue
                    if code >= 400:
                        raise RuntimeError(f"{provider} {code}: {resp.read().decode('utf-8', 'ignore')[:300]}")
                    for piece in iter_text_deltas(resp):
                        started_yielding = True
                        yield piece
                    if started_yielding:
                        return
                    last_err = f"{provider} key ...{key[-4:]} returned an empty stream"
                    logger.warning("%s; trying next key/provider.", last_err)
                    continue
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            if started_yielding:
                raise RuntimeError(f"{provider} stream interrupted: {type(exc).__name__}") from exc
            last_err = f"{provider} key ...{key[-4:]} " + ("timed out" if isinstance(exc, httpx.TimeoutException) else f"connection error: {type(exc).__name__}")
            _cool_down(provider, key, settings.LLM_KEY_COOLDOWN_SECONDS)
            logger.warning("%s; trying next key/provider.", last_err)
            continue

    raise TransientLLMError(f"{provider}: all {len(keys)} key(s) failed. Last error: {last_err}")
