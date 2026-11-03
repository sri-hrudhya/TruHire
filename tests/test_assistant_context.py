"""The assistant's model prompt is grounded in real practice / client / demand data and states what each word means."""
import uuid

from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_password_hash
from backend.database import SessionLocal
from backend.main import app
from backend.models import Conversation, ConversationMessage, Demand, Position, User, canonical_demand_id, get_next_position_display_id
from backend.routers import assistant
from backend.services.llm.assistant_context import GLOSSARY, NO_CLIENT, RULES, build_data_context


def _seed(db, user, practice, client_name, status="Open"):
    demand = db.query(Demand).filter(Demand.id == canonical_demand_id(practice)).first()
    if not demand:
        demand = Demand(id=canonical_demand_id(practice), name=practice)
        db.add(demand)
        db.flush()
    position = Position(display_id=get_next_position_display_id(db), title=f"Ctx {uuid.uuid4().hex[:6]}", jd_text="Needs skills.",
                        created_by=user.id, demand_id=demand.id, client_name=client_name, status=status)
    db.add(position)
    db.flush()
    return position


def test_glossary_separates_practice_from_demand_and_client():
    assert "Practice:" in GLOSSARY and "Demand / requirement / JD:" in GLOSSARY and "Client:" in GLOSSARY
    assert "not a practice" in GLOSSARY
    assert "ambiguous" in RULES and "Never invent" in RULES


def test_data_context_counts_live_demands_by_practice_and_client():
    db = SessionLocal()
    user = User(email=f"ctx-{uuid.uuid4().hex[:6]}@truhire.com", name="Ctx", hashed_password=get_password_hash("pass12345"))
    db.add(user)
    db.flush()
    try:
        before = build_data_context(db, "")
        _seed(db, user, "Pega", "Infosys")
        _seed(db, user, "Pega", None)
        _seed(db, user, "Java", "Infosys", status="Cancelled")
        db.flush()
        after = build_data_context(db, "how many demands for Infosys?")

        assert after["totals"]["all_requirements"] == before["totals"]["all_requirements"] + 3
        assert after["totals"]["live_requirements"] == before["totals"]["live_requirements"] + 2
        assert after["totals"]["cancelled"] == before["totals"]["cancelled"] + 1
        assert after["practices"]["Pega"]["Open"] == before["practices"].get("Pega", {}).get("Open", 0) + 2
        infosys = after["live_requirements_by_client"]["Infosys"]
        assert infosys.get("Pega", 0) == before["live_requirements_by_client"].get("Infosys", {}).get("Pega", 0) + 1
        assert infosys.get("Java", 0) == before["live_requirements_by_client"].get("Infosys", {}).get("Java", 0)  # cancelled is not live
        assert NO_CLIENT in after["live_requirements_by_client"]
        assert len(after["listed_requirements"]) <= 10
    finally:
        db.rollback()
        db.close()


def test_model_prompt_carries_glossary_and_data(monkeypatch):
    seen = []
    monkeypatch.setattr(assistant, "chat_completion_stream", lambda messages, **k: seen.append(messages) or iter(["ok"]))
    db = SessionLocal()
    user = User(email=f"ctx-{uuid.uuid4().hex[:6]}@truhire.com", name="Ctx", hashed_password=get_password_hash("pass12345"))
    db.add(user)
    db.commit()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    try:
        r = client.post("/api/assistant/message/stream", json={"message": "what is a practice versus a demand?"}, headers=headers)
        assert r.status_code == 200 and seen
        prompt = seen[0][0]["content"]
        assert GLOSSARY in prompt and RULES in prompt and "DATA:" in prompt and '"practices"' in prompt
        # Breakdown questions skip the keyword counter and reach the model, which has the full counts.
        seen.clear()
        r = client.post("/api/assistant/message/stream", json={"message": "how many demands per practice?"}, headers=headers)
        assert r.status_code == 200 and seen
    finally:
        ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == user.id).all()]
        db.query(ConversationMessage).filter(ConversationMessage.conversation_id.in_(ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
        db.close()
