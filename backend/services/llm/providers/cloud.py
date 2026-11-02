"""The cloud chat providers used when the DGX/vLLM box is unavailable, in fallback order."""
from __future__ import annotations

from backend.services.llm.providers._openai_compat import CloudProvider

OPENROUTER = CloudProvider(
    name="openrouter",
    endpoint="https://openrouter.ai/api/v1/chat/completions",
    key_settings=("OPENROUTER_API_KEY_1", "OPENROUTER_API_KEY_2", "OPENROUTER_API_KEY_3"),
    model_setting="OPENROUTER_CHAT_MODEL",
    extra_headers=(("HTTP-Referer", "https://truhire.app"), ("X-Title", "TruHire")),
)
GROQ = CloudProvider(
    name="groq",
    endpoint="https://api.groq.com/openai/v1/chat/completions",
    key_settings=("GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3"),
    model_setting="GROQ_MODEL",
)
GEMINI = CloudProvider(
    name="gemini",
    endpoint="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    key_settings=("GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"),
    model_setting="GEMINI_CHAT_MODEL",
)

CHAIN = (OPENROUTER, GROQ, GEMINI)
