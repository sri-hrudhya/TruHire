"""
OpenRouter chat completion provider.
OpenAI-compatible API: https://openrouter.ai/api/v1/chat/completions

Tries every OPENROUTER_API_KEY_1..3 (see _openai_compat.py) before giving up on the provider.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from backend.config import settings
from backend.services.llm.providers._openai_compat import chat_with_keys, stream_with_keys

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def model_name() -> str:
    return settings.OPENROUTER_CHAT_MODEL


def _keys() -> List[str]:
    return [
        k.strip()
        for k in (settings.OPENROUTER_API_KEY_1, settings.OPENROUTER_API_KEY_2, settings.OPENROUTER_API_KEY_3)
        if k and k.strip()
    ]


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    deadline: Optional[float] = None,
    **_ignored,  # absorbs vLLM-specific kwargs (e.g. enable_thinking)
) -> str:
    payload = {"model": settings.OPENROUTER_CHAT_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    return chat_with_keys(
        "openrouter", _ENDPOINT, _keys(), payload, deadline=deadline,
        extra_headers={"HTTP-Referer": "https://truhire.app", "X-Title": "TruHire"},
    )


def chat_completion_stream(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    deadline: Optional[float] = None,
    **_ignored,
) -> Iterator[str]:
    payload = {"model": model_name(), "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    return stream_with_keys("openrouter", _ENDPOINT, _keys(), payload, deadline=deadline, extra_headers={"HTTP-Referer": "https://truhire.app", "X-Title": "TruHire"})
