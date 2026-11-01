"""The assistant tells a resume from a demand document by content; no type picker needed."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_password_hash
from backend.database import SessionLocal
from backend.main import app
from backend.models import Conversation, ConversationMessage, IngestionBatch, User
from backend.routers import assistant
from backend.services.ingestion.doc_kind import detect_document_kind

JD = """Senior Java Developer
About the role
We are looking for a Senior Java Developer to join our payments team.
Roles and Responsibilities
- Design and build microservices with Spring Boot.
Required Skills
- 6+ years of experience in Java, Kafka and PostgreSQL.
Nice to have: Kubernetes.
No. of positions: 3. Location: Pune. Notice period should be under 30 days."""

RESUME = """Asha Verma
asha.verma@example.com | +91 98765 43210 | linkedin.com/in/ashaverma
Career Objective
Backend engineer with 6 years of experience.
Work Experience
Acme Pay, Senior Engineer, 2019 - Present. I built payment services in Java and led a team of four.
Education
B.Tech Computer Science, 2015
Certifications: AWS Developer Associate
Languages Known: English, Hindi"""


@pytest.mark.parametrize("name,text,expected", [
    ("opening.txt", JD, "jd"),
    ("asha.txt", RESUME, "resume"),
    ("jd_payments.txt", "Payments platform. Java, Kafka.", "jd"),       # file name is a signal too
    ("resume_asha.txt", "Java, Kafka, payments.", "resume"),
    ("jd_final.txt", RESUME, "resume"),                                  # content outweighs a misleading name
    ("notes.txt", "", "resume"),                                         # nothing readable: let ingestion (OCR) handle it
])
def test_detects_kind_from_content_and_name(name, text, expected):
    assert detect_document_kind(name, text) == expected


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr(assistant, "process_batch", lambda *a, **k: None)
    db = SessionLocal()
    user = User(email=f"kind-{uuid.uuid4().hex[:6]}@truhire.com", name="Kind Tester", hashed_password=get_password_hash("pass12345"))
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    yield TestClient(app), headers, db, user
    ids = [c.id for c in db.query(Conversation).filter(Conversation.user_id == user.id).all()]
    db.query(ConversationMessage).filter(ConversationMessage.conversation_id.in_(ids)).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
    db.query(IngestionBatch).filter(IngestionBatch.created_by == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    db.close()


def _upload(client, headers, name, text):
    return client.post("/api/assistant/upload", headers=headers, files={"file": (name, io.BytesIO(text.encode()), "text/plain")}).json()


def test_upload_without_a_type_goes_to_the_right_flow(ctx):
    client, headers, *_ = ctx
    assert _upload(client, headers, "opening.txt", JD)["action"] == "confirm_jd"
    assert _upload(client, headers, "asha.txt", RESUME)["action"] == "resume_ingestion"


def test_pasted_resume_is_not_turned_into_a_demand(ctx):
    client, headers, *_ = ctx
    r = client.post("/api/assistant/message", json={"message": RESUME}, headers=headers).json()
    assert r["action"] == "reply" and "looks like a resume" in r["reply"]
    r = client.post("/api/assistant/message", json={"message": JD}, headers=headers).json()
    assert r["action"] == "confirm_jd"
