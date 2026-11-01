"""Server-sent-events plumbing shared by the vLLM and cloud streaming chat calls."""
from __future__ import annotations

import json
from typing import Iterator

import httpx

from backend.services.llm.errors import TransientLLMError


def raise_for_stream_status(response: httpx.Response, who: str) -> None:
    """Map an HTTP error status of a streaming response (body not yet read) to the right error type."""
    if response.status_code < 400:
        return
    body = response.read().decode("utf-8", "ignore")[:300]
    if response.status_code >= 500 or response.status_code in (401, 403, 429):
        raise TransientLLMError(f"{who} returned HTTP {response.status_code}: {body}")
    raise RuntimeError(f"{who} returned {response.status_code}: {body}")


def iter_text_deltas(response: httpx.Response) -> Iterator[str]:
    """Yield the text pieces of an OpenAI-style `stream: true` response (`data: {...}` lines).
    Reasoning tokens (`reasoning`/`reasoning_content`) are not user-facing text and are skipped."""
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            choices = json.loads(data).get("choices") or []
        except ValueError:
            continue
        piece = ((choices[0].get("delta") or {}).get("content") if choices else None)
        if piece:
            yield piece
