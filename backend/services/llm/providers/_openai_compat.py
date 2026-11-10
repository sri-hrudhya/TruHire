"""OpenAI-compatible chat call with API-key rotation, shared by every cloud fallback provider.

Every configured key is tried before a provider is given up on: a timeout, connection error,
HTTP 429/401/403/5xx on one key moves on to the next key. Keys that just failed go on a short
cooldown so the next request does not wait on them again, and the first key tried rotates
round-robin so load is spread across keys.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

from backend.config import settings
from backend.services.llm.errors import TransientLLMError
from backend.services.llm.streaming import iter_text_deltas

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_next_start: Dict[str, int] = {}
_cooldown_until: Dict[str, float] = {}  # "<provider>:<key tail>" -> monotonic time
_BAD_KEY_COOLDOWN = 600  # 401/403: the key is invalid or revoked, do not retry it soon


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


class _KeyRun:
    """One pass over a provider's keys under an optional overall deadline (a ``time.monotonic()`` instant)."""

    def __init__(self, provider: str, keys: List[str], deadline: Optional[float]):
        if not keys:
            raise TransientLLMError(f"{provider}: no API keys configured.")
        self.provider, self.keys, self.deadline = provider, keys, deadline
        self.last_err = f"{provider}: unknown error."

    def __iter__(self) -> Iterator[Tuple[str, httpx.Timeout]]:
        for key in _ordered_keys(self.provider, self.keys):
            per_key = settings.LLM_CLOUD_KEY_TIMEOUT
            if self.deadline is not None:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0.5:
                    raise TransientLLMError(f"{self.provider}: overall time budget used up. Last error: {self.last_err}")
                per_key = min(per_key, remaining)
            yield key, httpx.Timeout(per_key, connect=min(settings.LLM_CONNECT_TIMEOUT, per_key))

    def failed(self, key: str, reason: str, cooldown: Optional[float] = None) -> None:
        self.last_err = f"{self.provider} key ...{key[-4:]} {reason}"
        _cool_down(self.provider, key, settings.LLM_KEY_COOLDOWN_SECONDS if cooldown is None else cooldown)
        logger.warning("%s; trying next key/provider.", self.last_err)

    def failed_status(self, key: str, code: int) -> bool:
        """Record a rotate-worthy HTTP status; False when the status should not rotate."""
        if code in (401, 403):
            self.failed(key, f"returned HTTP {code}", _BAD_KEY_COOLDOWN)
        elif code == 429 or code >= 500:
            self.failed(key, f"returned HTTP {code}")
        else:
            return False
        return True

    def failed_transport(self, key: str, exc: httpx.HTTPError, per_key: float) -> None:
        if isinstance(exc, httpx.TimeoutException):
            self.failed(key, f"timed out after {per_key:.0f}s")
        else:
            self.failed(key, f"connection error: {type(exc).__name__}")

    def exhausted(self) -> TransientLLMError:
        return TransientLLMError(f"{self.provider}: all {len(self.keys)} key(s) failed. Last error: {self.last_err}")


@dataclass(frozen=True)
class CloudProvider:
    """A cloud chat provider: endpoint, the settings holding its keys and model, optional extra headers."""
    name: str
    endpoint: str
    key_settings: Tuple[str, ...]
    model_setting: str
    extra_headers: Tuple[Tuple[str, str], ...] = ()

    def keys(self) -> List[str]:
        return [k.strip() for k in (getattr(settings, s) for s in self.key_settings) if k and k.strip()]

    def model_name(self) -> str:
        return getattr(settings, self.model_setting)

    def _request(self, key: str, messages: List[Dict[str, Any]], temperature: float, max_tokens: int, stream: bool,
                 tools: Optional[List[Dict[str, Any]]] = None) -> Tuple[Dict[str, str], Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **dict(self.extra_headers)}
        payload = {"model": self.model_name(), "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
        return headers, ({**payload, "stream": True} if stream else payload)

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        deadline: Optional[float] = None,
        **_ignored,  # absorbs vLLM-specific kwargs (e.g. enable_thinking)
    ) -> str:
        content = self.chat_message(messages, temperature=temperature, max_tokens=max_tokens, deadline=deadline).get("content")
        return "" if content is None else str(content)

    def chat_message(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        deadline: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """The assistant message (``content`` and, with ``tools``, ``tool_calls``) from the first key that answers."""
        run = _KeyRun(self.name, self.keys(), deadline)
        for key, timeout in run:
            headers, payload = self._request(key, messages, temperature, max_tokens, stream=False, tools=tools)
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(self.endpoint, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                run.failed_transport(key, exc, timeout.read)
                continue
            if run.failed_status(key, resp.status_code):
                continue
            if resp.status_code >= 400:
                # Bad request / unknown model: identical on every key, so stop rotating.
                raise RuntimeError(f"{self.name} {resp.status_code}: {resp.text[:300]}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise RuntimeError(f"{self.name} returned invalid JSON: {resp.text[:300]}") from exc
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"{self.name} returned no choices.")
            return choices[0].get("message") or {}
        raise run.exhausted()

    def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        deadline: Optional[float] = None,
        **_ignored,
    ) -> Iterator[str]:
        """Yield reply pieces as they arrive. Keys rotate as in chat_completion until the first piece; the
        timeout is the wait for each piece, so a key that connects but never answers is skipped after
        LLM_CLOUD_KEY_TIMEOUT. Once a piece has been yielded the reply is committed to that key and a later
        failure ends the stream with a plain RuntimeError (the router must not restart a half-delivered answer)."""
        run = _KeyRun(self.name, self.keys(), deadline)
        for key, timeout in run:
            headers, payload = self._request(key, messages, temperature, max_tokens, stream=True)
            started = False
            try:
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("POST", self.endpoint, headers=headers, json=payload) as resp:
                        if run.failed_status(key, resp.status_code):
                            continue
                        if resp.status_code >= 400:
                            raise RuntimeError(f"{self.name} {resp.status_code}: {resp.read().decode('utf-8', 'ignore')[:300]}")
                        for piece in iter_text_deltas(resp):
                            started = True
                            yield piece
                        if started:
                            return
                        run.failed(key, "returned an empty stream")
            except httpx.HTTPError as exc:
                if started:
                    raise RuntimeError(f"{self.name} stream interrupted: {type(exc).__name__}") from exc
                run.failed_transport(key, exc, timeout.read)
        raise run.exhausted()
