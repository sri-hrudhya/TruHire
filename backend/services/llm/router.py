"""DGX/vLLM-only chat client.

All generated TruHire text uses the OpenAI-compatible vLLM endpoint configured by
``VLLM_BASE_URL``. Cloud provider modules are intentionally not part of the
runtime path.
"""
from __future__ import annotations

from typing import Dict, List

from backend.services.llm import vllm as _vllm


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
    enable_thinking: bool = True,
) -> str:
    """
    Send a chat completion request to the configured DGX/vLLM endpoint.
    """
    return _vllm.chat_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )
