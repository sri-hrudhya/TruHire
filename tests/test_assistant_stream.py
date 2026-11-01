"""POST /api/assistant/message/stream: text arrives as SSE `token` events, then one `done` event."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_password_hash
from backend.database import SessionLocal
from backend.main import app
from backend.models import Conversation, ConversationMessage, User
from backend.routers import assistant


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


@pytest.fixture
def ctx():
    db = SessionLocal()
    user = User(email=f"stream-{uuid.uuid4().hex[:6]}@truhire.com", name="Stream Tester", hashed_password=get_password_hash("pass12345"))
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    yield TestClient(app), headers, db, user
    ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == user.id).all()]
    db.query(ConversationMessage).filter(ConversationMessage.conversation_id.in_(ids)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    db.close()


def test_free_text_answer_streams_then_saves(ctx, monkeypatch):
    client, headers, db, user = ctx
    monkeypatch.setattr(assistant, "chat_completion_stream", lambda *a, **k: iter(["You can ", "upload a ", "resume."]))
    r = client.post("/api/assistant/message/stream", json={"message": "what can you do?"}, headers=headers)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    assert [n for n, _ in events] == ["token", "token", "token", "done"]
    done = events[-1][1]
    assert done["reply"] == "You can upload a resume." and done["action"] == "reply"
    saved = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == done["conversation_id"], ConversationMessage.role == "assistant").one()
    assert saved.content == "You can upload a resume."


def test_deterministic_action_skips_the_llm(ctx, monkeypatch):
    client, headers, *_ = ctx
    monkeypatch.setattr(assistant, "chat_completion_stream", lambda *a, **k: pytest.fail("LLM must not be called"))
    r = client.post("/api/assistant/message/stream", json={"message": "show candidates"}, headers=headers)
    events = _events(r.text)
    assert [n for n, _ in events] == ["done"] and events[0][1]["action"] == "choose_position"


def test_failure_before_any_text_gives_the_help_message(ctx, monkeypatch):
    client, headers, *_ = ctx
    def dead(*a, **k):
        raise RuntimeError("all providers down")
        yield
    monkeypatch.setattr(assistant, "chat_completion_stream", dead)
    events = _events(client.post("/api/assistant/message/stream", json={"message": "hello there"}, headers=headers).text)
    assert [n for n, _ in events] == ["done"] and "ingest resumes" in events[0][1]["reply"]


def test_interrupted_answer_keeps_partial_text_and_reports_error(ctx, monkeypatch):
    client, headers, *_ = ctx
    def half(*a, **k):
        yield "Partial answer"
        raise RuntimeError("stream interrupted")
    monkeypatch.setattr(assistant, "chat_completion_stream", half)
    events = _events(client.post("/api/assistant/message/stream", json={"message": "hello there"}, headers=headers).text)
    assert [n for n, _ in events] == ["token", "error", "done"] and events[-1][1]["reply"] == "Partial answer"
