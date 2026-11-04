import uuid

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import Candidate, IngestionBatch, User
from backend.routers import ingestion as ing


@pytest.fixture(scope="module")
def auth():
    client = TestClient(app)
    tag = uuid.uuid4().hex[:8]
    email = f"dup.{tag}@example.com"
    client.post("/api/auth/register", json={"email": email, "name": "Dup Tester", "password": "pass-1234-xyz"})
    token = client.post("/api/auth/login", json={"email": email, "password": "pass-1234-xyz"}).json()["access_token"]
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()
    return {"client": client, "headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "tag": tag}


def _stub_pipeline(monkeypatch, name="Cand"):
    monkeypatch.setattr(ing, "parse_resume", lambda text, fn: {
        "candidate_name": f"{name} {fn}", "email": None, "phone": None, "extracted_skills": ["Python"],
        "years_experience": 3.0, "education": "BSc"})
    monkeypatch.setattr(ing, "generate_embeddings_batch", lambda texts: [[0.1] * 8 for _ in texts])
    monkeypatch.setattr(ing, "upsert_candidates_batch", lambda items: None)
    monkeypatch.setattr(ing, "index_candidates_batch", lambda items: None)


def _run(auth, files, actions=None):
    db = SessionLocal()
    b = IngestionBatch(created_by=auth["user_id"], total_files=len(files), status="processing", error_log=[], stage="queued",
                       file_status=[{"filename": n, "status": "queued", "detail": ""} for n, _ in files])
    db.add(b); db.commit()
    bid = b.id
    db.close()
    ing.process_batch(bid, files, auth["user_id"], actions)
    return auth["client"].get(f"/api/ingest/batches/{bid}", headers=auth["headers"]).json()


def _candidates(body):
    db = SessionLocal()
    try:
        return db.query(Candidate).filter(Candidate.file_hash == ing.compute_file_hash(body)).order_by(Candidate.uploaded_at).all(), body
    finally:
        db.close()


def _check(auth, files):
    return auth["client"].post("/api/ingest/check-duplicates", headers=auth["headers"],
                               files=[("files", (n, b)) for n, b in files]).json()["duplicates"]


def test_check_duplicates_reports_existing_and_ignores_new(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    body = f"Python engineer {auth['tag']}".encode()
    name = f"a-{auth['tag']}.txt"
    _run(auth, [(name, body)])
    dups = _check(auth, [(f"renamed-{auth['tag']}.txt", body), (f"new-{auth['tag']}.txt", b"completely different " + auth["tag"].encode())])
    assert len(dups) == 1
    assert dups[0]["filename"] == f"renamed-{auth['tag']}.txt"
    assert dups[0]["uploaded_at"].endswith("Z") and dups[0]["uploaded_by"] == "Dup Tester"


def test_check_duplicates_returns_newest_when_hash_matches_several(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    body = f"Java dev {auth['tag']}".encode()
    _run(auth, [(f"first-{auth['tag']}.txt", body)])
    db = SessionLocal()
    old = db.query(Candidate).filter(Candidate.file_hash == ing.compute_file_hash(body)).first()
    db.add(Candidate(display_id=f"X-{auth['tag']}", candidate_name="Newer copy", resume_text="x", status="New", uploaded_by=auth["user_id"],
                     file_hash=old.file_hash, original_filename="newer.txt", extracted_skills=[]))
    db.commit(); db.close()
    dups = _check(auth, [("probe.txt", body)])
    assert dups[0]["candidate_name"] == "Newer copy"


def test_default_skip_leaves_candidate_unchanged(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    body = f"Skip me {auth['tag']}".encode()
    _run(auth, [(f"s1-{auth['tag']}.txt", body)])
    status = _run(auth, [(f"s2-{auth['tag']}.txt", body)])
    cands, _ = _candidates(body)
    assert len(cands) == 1
    assert status["file_status"][0]["status"] == "duplicate"


def test_update_keeps_same_candidate_and_refreshes_it(auth, monkeypatch):
    _stub_pipeline(monkeypatch, name="Old")
    body = f"Update me {auth['tag']}".encode()
    _run(auth, [(f"u1-{auth['tag']}.txt", body)])
    before, _ = _candidates(body)
    _stub_pipeline(monkeypatch, name="New")
    name2 = f"u2-{auth['tag']}.txt"
    status = _run(auth, [(name2, body)], {name2: "update"})
    after, _ = _candidates(body)
    assert len(after) == 1 and after[0].id == before[0].id and after[0].display_id == before[0].display_id
    assert after[0].candidate_name == f"New {name2}"
    assert after[0].uploaded_at > before[0].uploaded_at
    assert status["file_status"][0]["status"] == "updated"


def test_update_with_same_file_twice_in_batch_updates_once(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    body = f"Twice {auth['tag']}".encode()
    _run(auth, [(f"t0-{auth['tag']}.txt", body)])
    a, b = f"ta-{auth['tag']}.txt", f"tb-{auth['tag']}.txt"
    status = _run(auth, [(a, body), (b, body)], {a: "update", b: "update"})
    assert [f["status"] for f in status["file_status"]] == ["updated", "duplicate"]
    assert len(_candidates(body)[0]) == 1


def test_update_failing_to_parse_keeps_old_record(auth, monkeypatch):
    _stub_pipeline(monkeypatch, name="Keep")
    body = f"Keep me {auth['tag']}".encode()
    _run(auth, [(f"k1-{auth['tag']}.txt", body)])
    before, _ = _candidates(body)

    def boom(text, fn):
        raise RuntimeError("llm down")
    monkeypatch.setattr(ing, "parse_resume", boom)
    name2 = f"k2-{auth['tag']}.txt"
    status = _run(auth, [(name2, body)], {name2: "update"})
    after, _ = _candidates(body)
    assert status["file_status"][0]["status"] == "failed"
    assert after[0].candidate_name == before[0].candidate_name


def test_invalid_duplicate_actions_means_skip():
    assert ing._parse_duplicate_actions("not json") == {}
    assert ing._parse_duplicate_actions('["a"]') == {}
    assert ing._parse_duplicate_actions('{"a.pdf":"update","b.pdf":"weird"}') == {"a.pdf": "update"}
