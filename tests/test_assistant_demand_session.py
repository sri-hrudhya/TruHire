"""Guided demand creation in the assistant: a server-side, schema-driven workflow."""
import io
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_password_hash
from backend.database import SessionLocal
from backend.main import app
from backend.models import AssistantDemandSession, Conversation, ConversationMessage, DEFAULT_DEMAND_NAMES, Position, User, canonical_demand_id
from backend.routers import assistant_demand
from backend.services.common import demand_fields as df

JD = """Senior Java Developer
We are looking for a Senior Java Developer for our payments team.
Required Skills
- 6+ years of experience in Java, Kafka and PostgreSQL.
No. of positions: 3. Location: Pune."""

PREFIX = "/api/assistant/demand-sessions"


def _user(db, label):
    user = User(email=f"{label}-{uuid.uuid4().hex[:6]}@truhire.com", name=label.title(), hashed_password=get_password_hash("pass12345"))
    db.add(user)
    db.commit()
    return user, {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}


@pytest.fixture
def ctx():
    db = SessionLocal()
    (user, headers), (other, other_headers) = _user(db, "demand-a"), _user(db, "demand-b")
    client = TestClient(app)
    yield client, headers, other_headers, db, user
    for u in (user, other):
        ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == u.id).all()]
        db.query(AssistantDemandSession).filter(AssistantDemandSession.conversation_id.in_(ids)).delete(synchronize_session=False)
        db.query(ConversationMessage).filter(ConversationMessage.conversation_id.in_(ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == u.id).delete(synchronize_session=False)
    created = db.query(Position).filter(Position.created_by.in_([user.id, other.id])).all()
    for position in created:
        client.delete(f"/api/job-descriptions/{position.id}", headers=headers)
    db.expire_all()
    db.query(Position).filter(Position.created_by.in_([user.id, other.id])).delete(synchronize_session=False)
    for u in (user, other):
        try:
            db.delete(u)
            db.commit()
        except Exception:
            db.rollback()
    db.close()


def _start(client, headers):
    r = client.post("/api/assistant/message", json={"message": "Create a new demand"}, headers=headers).json()
    assert r["action"] == "demand_session"
    return r["session"], r["conversation_id"]


def _op(client, headers, session, op, body=None, expect=200):
    r = client.post(f"{PREFIX}/{session['id']}/{op}", json=body or {}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def _fill_required(client, headers, session):
    session = _op(client, headers, session, "mode", {"mode": "step_by_step"})["session"]
    assert session["current_field"] == "title"
    for key, value in (("title", "Java Lead"), ("demand_id", "Java")):
        session = _op(client, headers, session, "answer", {"value": value})["session"]
    while session["status"] == "collecting":
        field = next(f for f in session["fields"] if f["key"] == session["current_field"])
        body = {"value": "Spring Boot microservices engineer."} if field["key"] == "jd_text" else {}
        session = _op(client, headers, session, "answer" if body else "skip", body)["session"]
    return session


def test_fields_follow_the_new_demand_form_with_real_options(ctx):
    client, headers, *_ = ctx
    fields = client.get(f"{PREFIX}/fields", headers=headers).json()["fields"]
    assert [f["key"] for f in fields] == ["title", "demand_id", "client_name", "experience_years", "experience_max_years",
                                         "locations", "no_of_positions", "start_date", "end_date", "jd_text"]
    assert [f["label"] for f in fields if f["required"]] == ["Title", "Demand Practice", "Specification"]
    practice = next(f for f in fields if f["key"] == "demand_id")
    assert [o["label"] for o in practice["options"]] == list(DEFAULT_DEMAND_NAMES)
    assert next(f for f in fields if f["key"] == "client_name")["options"]
    assert not any("work_mode" == f["key"] or f["key"] == "status" for f in fields)


def test_chat_request_starts_a_session_and_offers_exactly_two_modes(ctx):
    client, headers, *_ = ctx
    session, conversation_id = _start(client, headers)
    assert session["status"] == "choose_mode" and session["input_mode"] is None
    assert client.post(f"{PREFIX}/{session['id']}/mode", json={"mode": "chat"}, headers=headers).status_code == 422
    again = client.post("/api/assistant/message", json={"message": "create a demand", "conversation_id": conversation_id}, headers=headers).json()
    assert again["session"]["id"] == session["id"]  # one active session per conversation


def test_step_by_step_asks_one_field_at_a_time_in_form_order(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    out = _op(client, headers, session, "mode", {"mode": "step_by_step"})
    session = out["session"]
    assert session["current_field"] == "title" and session["progress"] == {"step": 1, "total": 10}
    assert out["messages"][-1]["content"] == "What is the demand title?"
    # fields cannot be answered out of order
    _op(client, headers, session, "answer", {"field": "jd_text", "value": "text"}, expect=409)
    session = _op(client, headers, session, "answer", {"value": "Java Lead"})["session"]
    assert session["current_field"] == "demand_id" and session["progress"]["step"] == 2
    # invalid choice: same field stays open, nothing is stored, the reason is shown
    out = _op(client, headers, session, "answer", {"value": "Python"})
    assert out["session"]["current_field"] == "demand_id"
    assert "Choose one of" in out["messages"][-1]["content"] and out["session"]["fields"][1]["error"]
    out = _op(client, headers, session, "answer", {"value": "java"})
    assert out["session"]["current_field"] == "client_name"
    assert next(f for f in out["session"]["fields"] if f["key"] == "title")["value"] == "Java Lead"
    # required fields cannot be skipped; optional ones can
    session = _op(client, headers, out["session"], "skip")["session"]  # client is optional
    assert session["current_field"] == "experience_years"


def test_invalid_answers_are_rejected_with_schema_messages(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    session = _op(client, headers, session, "mode", {"mode": "step_by_step"})["session"]
    assert _op(client, headers, session, "skip", expect=422)  # Title is required
    session = _op(client, headers, session, "answer", {"value": "T"})["session"]
    session = _op(client, headers, session, "answer", {"value": "Pega"})["session"]
    session = _op(client, headers, session, "skip")["session"]  # client
    out = _op(client, headers, session, "answer", {"value": "99"})  # min experience out of range
    assert out["session"]["current_field"] == "experience_years" and "60" in out["messages"][-1]["content"]
    session = _op(client, headers, session, "answer", {"value": "5"})["session"]
    out = _op(client, headers, session, "answer", {"value": "3"})  # max below min
    assert out["session"]["current_field"] == "experience_max_years" and "Max experience" in out["messages"][-1]["content"]


def test_all_fields_mode_keeps_valid_values_when_some_fail(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    session = _op(client, headers, session, "mode", {"mode": "all_fields"})["session"]
    out = _op(client, headers, session, "answers", {"values": {"title": "Pega Architect", "demand_id": "Pega", "jd_text": "Pega work",
                                                              "start_date": "2026-12-01", "end_date": "2026-11-01", "experience_years": "abc"}})
    s = out["session"]
    values = {f["key"]: f["value"] for f in s["fields"]}
    errors = {f["key"]: f["error"] for f in s["fields"] if f["error"]}
    assert s["status"] == "collecting" and values["title"] == "Pega Architect" and values["demand_id"] == canonical_demand_id("Pega")
    assert set(errors) == {"end_date", "experience_years"}
    out = _op(client, headers, s, "answers", {"values": {"end_date": "2027-01-01", "experience_years": "4"}})
    assert out["session"]["status"] == "review"
    missing = _op(client, headers, _op(client, headers, session, "mode", {"mode": "all_fields"})["session"], "answers", {"values": {"title": ""}})
    assert "Title" in missing["messages"][-1]["content"] or missing["session"]["status"] == "review"


def test_document_prefills_only_what_it_states_and_step_mode_skips_it(ctx):
    client, headers, *_ = ctx
    r = client.post("/api/assistant/upload", headers=headers, files={"file": ("opening.txt", io.BytesIO(JD.encode()), "text/plain")}).json()
    assert r["action"] == "demand_session"
    s = r["session"]
    values = {f["key"]: f["value"] for f in s["fields"]}
    assert values["jd_text"].startswith("Senior Java Developer") and values["demand_id"] == canonical_demand_id("Java")
    assert values["client_name"] is None and values["start_date"] is None  # never invented
    assert next(f for f in s["fields"] if f["key"] == "jd_text")["source"] == "document"
    s = _op(client, headers, s, "mode", {"mode": "step_by_step"})["session"]
    asked = []
    while s["status"] == "collecting":
        asked.append(s["current_field"])
        s = _op(client, headers, s, "skip" if not df.BY_KEY[s["current_field"]]["required"] else "answer", {"value": "Lead"})["session"]
    assert "jd_text" not in asked and "demand_id" not in asked and s["status"] == "review"


def test_unreadable_document_is_reported_not_guessed(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    r = client.post(f"{PREFIX}/{session['id']}/document", headers=headers, files={"file": ("empty.txt", io.BytesIO(b"   "), "text/plain")})
    assert r.status_code == 200 and "couldn't read any text" in r.json()["messages"][-1]["content"]
    assert all(f["value"] is None for f in r.json()["session"]["fields"])
    r = client.post(f"{PREFIX}/{session['id']}/document", headers=headers, files={"file": ("x.exe", io.BytesIO(b"abc"), "application/octet-stream")})
    assert r.status_code == 400


def test_edit_back_and_switching_modes_keep_answers(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    session = _fill_required(client, headers, session)
    assert session["status"] == "review"
    s = _op(client, headers, session, "edit", {"field": "title"})["session"]
    assert s["status"] == "collecting" and s["current_field"] == "title"
    s = _op(client, headers, s, "answer", {"value": "Renamed Demand"})["session"]
    assert s["status"] == "review" and next(f for f in s["fields"] if f["key"] == "title")["value"] == "Renamed Demand"
    s = _op(client, headers, s, "mode", {"mode": "all_fields"})["session"]
    assert s["input_mode"] == "all_fields" and next(f for f in s["fields"] if f["key"] == "demand_id")["value"] == canonical_demand_id("Java")
    s = _op(client, headers, s, "mode", {"mode": "step_by_step"})["session"]
    assert s["status"] == "review"


def test_back_returns_to_the_previous_field(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    s = _op(client, headers, session, "mode", {"mode": "step_by_step"})["session"]
    s = _op(client, headers, s, "answer", {"value": "A title"})["session"]
    assert s["current_field"] == "demand_id"
    s = _op(client, headers, s, "back")["session"]
    assert s["current_field"] == "title"
    s = _op(client, headers, s, "answer", {"value": "Better title"})["session"]
    assert s["current_field"] == "demand_id"
    _op(client, headers, _op(client, headers, session, "back")["session"], "back", expect=409)


def test_typed_text_is_an_answer_or_a_command(ctx):
    client, headers, *_ = ctx
    session, _ = _start(client, headers)
    s = _op(client, headers, session, "message", {"text": "one by one"})["session"]
    assert s["input_mode"] == "step_by_step"
    s = _op(client, headers, s, "message", {"text": "Typed Title"})["session"]
    assert s["current_field"] == "demand_id"
    s = _op(client, headers, s, "message", {"text": "back"})["session"]
    assert s["current_field"] == "title"
    out = _op(client, headers, s, "message", {"text": "cancel"})
    assert out["session"]["status"] == "cancelled"


def test_sessions_are_private_to_their_user(ctx):
    client, headers, other_headers, *_ = ctx
    session, conversation_id = _start(client, headers)
    for op, method in (("", "get"), ("/answer", "post"), ("/confirm", "post"), ("/cancel", "post")):
        r = getattr(client, method)(f"{PREFIX}/{session['id']}{op}", headers=other_headers, **({"json": {"value": "x"}} if method == "post" else {}))
        assert r.status_code == 404
    # a second conversation has its own, independent session
    other_session, other_conversation = _start(client, other_headers)
    assert other_session["id"] != session["id"] and other_conversation != conversation_id
    assert client.post(PREFIX, json={"conversation_id": conversation_id}, headers=other_headers).status_code == 404
    assert client.get(f"{PREFIX}/{session['id']}", headers={}).status_code in (401, 403)


def test_session_survives_reopening_the_conversation(ctx):
    client, headers, *_ = ctx
    session, conversation_id = _start(client, headers)
    session = _op(client, headers, session, "mode", {"mode": "step_by_step"})["session"]
    _op(client, headers, session, "answer", {"value": "Persisted Title"})
    detail = client.get(f"/api/assistant/conversations/{conversation_id}", headers=headers).json()
    restored = detail["demand_session"]
    assert restored["id"] == session["id"] and restored["current_field"] == "demand_id" and restored["progress"]["step"] == 2
    assert next(f for f in restored["fields"] if f["key"] == "title")["value"] == "Persisted Title"
    assert any(m["content"] == "Persisted Title" for m in detail["messages"])


def test_confirm_creates_once_and_only_after_review(ctx):
    client, headers, _, db, user = ctx
    session, _ = _start(client, headers)
    _op(client, headers, session, "confirm", expect=409)  # not reviewed yet
    session = _fill_required(client, headers, session)
    before = db.query(Position).filter(Position.created_by == user.id).count()
    out = _op(client, headers, session, "confirm")
    assert out["created"]["display_id"] and "created successfully" in out["messages"][-1]["content"]
    again = _op(client, headers, session, "confirm")  # a repeated click or retry
    assert again["created"]["id"] == out["created"]["id"]
    db.expire_all()
    assert db.query(Position).filter(Position.created_by == user.id).count() == before + 1
    created = db.query(Position).filter(Position.id == out["created"]["id"]).first()
    assert created.title == "Java Lead" and created.demand_id == canonical_demand_id("Java") and created.status == "Open"
    assert created.no_of_positions == 1  # the form's default


def test_failed_creation_keeps_the_answers_and_reports_no_success(ctx, monkeypatch):
    client, headers, _, db, user = ctx
    session, _ = _start(client, headers)
    session = _fill_required(client, headers, session)

    def boom(*a, **k):
        raise HTTPException(422, "Backend says no.")
    monkeypatch.setattr(assistant_demand, "create_jd", boom)
    r = client.post(f"{PREFIX}/{session['id']}/confirm", headers=headers)
    assert r.status_code == 422 and "Backend says no." in r.text
    state = client.get(f"{PREFIX}/{session['id']}", headers=headers).json()["session"]
    assert state["status"] == "review" and next(f for f in state["fields"] if f["key"] == "title")["value"] == "Java Lead"
    db.expire_all()
    assert db.query(Position).filter(Position.created_by == user.id).count() == 0
    monkeypatch.undo()
    assert _op(client, headers, state, "confirm")["created"]["id"]


def test_cancellation_creates_nothing(ctx):
    client, headers, _, db, user = ctx
    session, _ = _start(client, headers)
    session = _fill_required(client, headers, session)
    out = _op(client, headers, session, "cancel")
    assert out["session"]["status"] == "cancelled" and "Nothing was created" in out["messages"][-1]["content"]
    _op(client, headers, session, "confirm", expect=409)
    db.expire_all()
    assert db.query(Position).filter(Position.created_by == user.id).count() == 0
    assert client.get(f"/api/assistant/conversations/{out['session']['conversation_id']}", headers=headers).json()["demand_session"] is None


def test_pasted_jd_starts_a_prefilled_session(ctx):
    client, headers, *_ = ctx
    r = client.post("/api/assistant/message", json={"message": JD + "\n" + "Extra detail. " * 20}, headers=headers).json()
    assert r["action"] == "demand_session"
    values = {f["key"]: f["value"] for f in r["session"]["fields"]}
    assert values["demand_id"] == canonical_demand_id("Java") and values["jd_text"]


def test_normalize_uses_the_demand_schema():
    db = SessionLocal()
    try:
        assert df.normalize("no_of_positions", "2.5", db)[1]
        assert df.normalize("no_of_positions", "3", db) == (3, None)
        assert df.normalize("locations", "Pune, pune, Mumbai", db) == (["Pune", "Mumbai"], None)
        assert df.normalize("start_date", "15/11/2026", db) == ("2026-11-15", None)
        assert df.normalize("start_date", "someday", db)[1]
        assert df.normalize("client_name", "infosys", db) == ("Infosys", None)
        assert df.normalize("client_name", "Acme Corp", db) == ("Acme Corp", None)  # "Others": a typed client
        assert df.normalize("title", "   ", db)[1] == "Title is required."
        assert df.cross_check({"start_date": "2026-12-01", "end_date": "2026-11-01"})
    finally:
        db.close()
