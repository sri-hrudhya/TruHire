"""Typed LLM errors so the chat router can tell "try the next provider" from "real failure"."""
from __future__ import annotations


class TransientLLMError(RuntimeError):
    """Infrastructure failure (cannot connect, timeout, HTTP 5xx/429). Worth trying another key or provider."""
