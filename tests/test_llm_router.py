"""Chat fallback chain: vLLM first, then every key of OpenRouter, Groq and Gemini."""
import httpx
import pytest

from backend.config import settings
from backend.services.llm import router, vllm
from backend.services.llm.errors import TransientLLMError
from backend.services.llm.providers import _openai_compat as compat

MSGS = [{"role": "user", "content": "Reach me at jane.doe@example.com or +1 415 555 0100"}]


def _ok(text="cloud answer"):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


@pytest.fixture
def chain(monkeypatch):
    """Three keys per provider; `behaviour` maps '<host>:<key>' to a response or an exception."""
    for prefix in ("OPENROUTER", "GROQ", "GEMINI"):
        for i in (1, 2, 3):
            monkeypatch.setattr(settings, f"{prefix}_API_KEY_{i}", f"{prefix.lower()}-key-{i}")
    monkeypatch.setattr(settings, "LLM_CLOUD_REDACT_PII", True)
    router._vllm_succeeded()
    compat._next_start.clear()
    compat._cooldown_until.clear()
    seen = []
    behaviour = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].split()[1]
        seen.append((request.url.host, key, request.content.decode()))
        outcome = behaviour.get(key, _ok())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    real_client = httpx.Client
    monkeypatch.setattr(compat.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(vllm, "chat_completion", lambda *a, **k: (_ for _ in ()).throw(TransientLLMError("Could not connect to DGX vLLM.")))
    return seen, behaviour


def test_vllm_answer_wins_and_cloud_is_not_called(chain, monkeypatch):
    seen, _ = chain
    monkeypatch.setattr(vllm, "chat_completion", lambda *a, **k: "dgx answer")
    assert router.chat_completion(MSGS) == "dgx answer"
    assert seen == []


def test_every_key_of_a_provider_is_tried_before_the_next_provider(chain):
    seen, behaviour = chain
    behaviour["openrouter-key-1"] = httpx.ReadTimeout("slow")
    behaviour["openrouter-key-2"] = httpx.Response(429, json={})
    behaviour["openrouter-key-3"] = httpx.Response(503, json={})
    assert router.chat_completion(MSGS) == "cloud answer"
    assert [k for _, k, _ in seen] == ["openrouter-key-1", "openrouter-key-2", "openrouter-key-3", "groq-key-1"]


def test_falls_through_to_gemini_when_other_providers_fail(chain):
    seen, behaviour = chain
    for prefix in ("openrouter", "groq"):
        for i in (1, 2, 3):
            behaviour[f"{prefix}-key-{i}"] = httpx.ConnectTimeout("down")
    assert router.chat_completion(MSGS) == "cloud answer"
    assert seen[-1][1].startswith("gemini-key-")
    assert len(seen) == 7


def test_raises_when_all_providers_fail(chain):
    _, behaviour = chain
    for prefix in ("openrouter", "groq", "gemini"):
        for i in (1, 2, 3):
            behaviour[f"{prefix}-key-{i}"] = httpx.Response(500, json={})
    with pytest.raises(TransientLLMError):
        router.chat_completion(MSGS)


def test_pii_is_redacted_before_leaving_for_the_cloud(chain):
    seen, _ = chain
    router.chat_completion(MSGS)
    body = seen[0][2]
    assert "jane.doe@example.com" not in body and "555 0100" not in body
    assert "[EMAIL]" in body


def test_first_key_rotates_round_robin(chain):
    seen, _ = chain
    router.chat_completion(MSGS)
    router.chat_completion(MSGS)
    assert [k for _, k, _ in seen] == ["openrouter-key-1", "openrouter-key-2"]


def test_failed_key_is_tried_last_on_the_next_request(chain):
    seen, behaviour = chain
    behaviour["openrouter-key-1"] = httpx.ReadTimeout("slow")
    router.chat_completion(MSGS)
    seen.clear()
    compat._next_start.clear()
    router.chat_completion(MSGS)
    assert seen[0][1] == "openrouter-key-2"


def test_dead_vllm_is_skipped_after_repeated_failures(chain, monkeypatch):
    calls = []
    monkeypatch.setattr(vllm, "chat_completion", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(TransientLLMError("down")))
    for _ in range(4):
        router.chat_completion(MSGS)
    assert len(calls) == settings.LLM_VLLM_BREAKER_FAILURES


def test_non_transient_vllm_error_is_not_masked(chain, monkeypatch):
    monkeypatch.setattr(vllm, "chat_completion", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DGX vLLM returned 400: bad")))
    with pytest.raises(RuntimeError, match="400"):
        router.chat_completion(MSGS)


# ---- streaming ----

def _sse_body(*pieces):
    lines = [f'data: {{"choices":[{{"delta":{{"content":"{p}"}}}}]}}' for p in pieces] + ["data: [DONE]"]
    return "\n\n".join(lines) + "\n\n"


def _stream_ok(*pieces):
    return httpx.Response(200, content=_sse_body(*pieces).encode(), headers={"content-type": "text/event-stream"})


def test_vllm_stream_is_passed_through_piece_by_piece(chain, monkeypatch):
    seen, _ = chain
    monkeypatch.setattr(vllm, "chat_completion_stream", lambda *a, **k: iter(["Hel", "lo"]))
    assert list(router.chat_completion_stream(MSGS)) == ["Hel", "lo"]
    assert seen == []


def test_stream_falls_back_to_cloud_and_rotates_keys_before_first_piece(chain, monkeypatch):
    seen, behaviour = chain
    monkeypatch.setattr(vllm, "chat_completion_stream", lambda *a, **k: (_ for _ in ()).throw(TransientLLMError("down")))
    behaviour["openrouter-key-1"] = httpx.ReadTimeout("slow")
    behaviour["openrouter-key-2"] = httpx.Response(429, json={})
    behaviour["openrouter-key-3"] = _stream_ok("Hi ", "there")
    assert "".join(router.chat_completion_stream(MSGS)) == "Hi there"
    assert [k for _, k, _ in seen] == ["openrouter-key-1", "openrouter-key-2", "openrouter-key-3"]
    assert '"stream":true' in seen[-1][2].replace(" ", "")
    assert "jane.doe@example.com" not in seen[-1][2]


def test_stream_moves_to_next_provider_when_all_keys_of_one_fail(chain, monkeypatch):
    seen, behaviour = chain
    monkeypatch.setattr(vllm, "chat_completion_stream", lambda *a, **k: (_ for _ in ()).throw(TransientLLMError("down")))
    for i in (1, 2, 3):
        behaviour[f"openrouter-key-{i}"] = httpx.Response(503, json={})
        behaviour[f"groq-key-{i}"] = _stream_ok("from groq")
    assert "".join(router.chat_completion_stream(MSGS)) == "from groq"


def test_stream_that_dies_midway_is_not_restarted_elsewhere(chain, monkeypatch):
    def half(*a, **k):
        yield "partial "
        raise TransientLLMError("connection dropped")
    monkeypatch.setattr(vllm, "chat_completion_stream", half)
    got = []
    with pytest.raises(RuntimeError, match="interrupted"):
        for piece in router.chat_completion_stream(MSGS):
            got.append(piece)
    assert got == ["partial "] and chain[0] == []
