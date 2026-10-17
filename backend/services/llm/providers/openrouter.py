"""
OpenRouter chat completion provider.
OpenAI-compatible API: https://openrouter.ai/api/v1/chat/completions

Rotates through OPENROUTER_API_KEY_1 / _2 on 429 rate-limit errors.
Raises RuntimeError with "unreachable" / "server error" text for transient
infrastructure failures so router.py can detect them and try the next provider.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT = 60.0


def _keys() -> List[str]:
    return [
        k.strip()
        for k in (settings.OPENROUTER_API_KEY_1, settings.OPENROUTER_API_KEY_2)
        if k and k.strip()
    ]


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    **_ignored,  # absorbs vLLM-specific kwargs (e.g. enable_thinking)
) -> str:
    keys = _keys()
    if not keys:
        raise RuntimeError(
            "OpenRouter: no API keys configured (OPENROUTER_API_KEY_1 / OPENROUTER_API_KEY_2)."
        )

    model = settings.OPENROUTER_CHAT_MODEL
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_err: Exception = RuntimeError("OpenRouter: unknown error.")
    for key in keys:
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(
                    _ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://truhire.app",
                        "X-Title": "TruHire",
                    },
                    json=payload,
                )
        except httpx.ConnectError as exc:
            raise RuntimeError(f"OpenRouter unreachable: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("OpenRouter request timed out.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenRouter HTTP error: {exc}") from exc

        if resp.status_code == 429:
            logger.warning("OpenRouter key rate-limited (429), rotating to next key.")
            last_err = RuntimeError("OpenRouter: all configured keys are rate-limited.")
            continue

        if resp.status_code >= 500:
            raise RuntimeError(
                f"OpenRouter server error {resp.status_code}: {resp.text[:300]}"
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"OpenRouter {resp.status_code}: {resp.text[:300]}"
            ) from exc

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"OpenRouter returned invalid JSON: {resp.text[:300]}"
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices. Response: {data}")

        content = choices[0].get("message", {}).get("content")
        return str(content) if content is not None else ""

    raise last_err
