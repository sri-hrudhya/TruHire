import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.main import app
from backend.models import Candidate, IngestionBatch, User
from backend.routers import ingestion as ing


@pytest.fixture
def auth():
    client = TestClient(app)
    tag = uuid.uuid4().hex[:8]
    email = f"hist.{tag}@example.com"
    client.post("/api/auth/register", json={"email": email, "name": "History Tester", "password": "pass-1234-xyz"})
    token = client.post("/api/auth/login", json={"email": email, "password": "pass-1234-xyz"}).json()["access_token"]
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()
    return {"client": client, "headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "tag": tag}


def _stub_pipeline(monkeypatch):
    monkeypatch.setattr(ing, "parse_resume", lambda text, name: {
        "candidate_name": f"Cand {name}", "email": None, "phone": None, "extracted_skills": ["Python"],
        "years_experience": 3.0, "education": "BSc"})
    monkeypatch.setattr(ing, "generate_embeddings_batch", lambda texts: [[0.1] * 8 for _ in texts])
    monkeypatch.setattr(ing, "upsert_candidates_batch", lambda items: None)
    monkeypatch.setattr(ing, "index_candidates_batch", lambda items: None)


def _make_batch(user_id, names):
    db = SessionLocal()
    b = IngestionBatch(created_by=user_id, total_files=len(names), status="processing", error_log=[], stage="queued",
                       file_status=[{"filename": n, "status": "queued", "detail": ""} for n in names])
    db.add(b); db.commit()
    bid = b.id
    db.close()
    return bid


def test_progress_is_reported_live_through_every_stage(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    snapshots = []
    original_flush = ing._Progress._flush

    def spy(self):
        original_flush(self)
        snapshots.append((self.batch.stage, {f["filename"]: f["status"] for f in self.files}))

    monkeypatch.setattr(ing._Progress, "_flush", spy)
    name = f"live-{auth['tag']}.txt"
    bid = _make_batch(auth["user_id"], [name])
    ing.process_batch(bid, [(name, f"Python developer {auth['tag']} with FastAPI experience".encode())], auth["user_id"])

    seen = [s[1][name] for s in snapshots]
    # Each stage is visible, in order, before the file ends as indexed.
    order = ["extracting", "analyzing", "parsed", "embedding", "indexing", "indexed"]
    positions = [seen.index(st) for st in order]
    assert positions == sorted(positions), seen
    assert {s[0] for s in snapshots} >= {"reading", "embedding", "indexing"}

    status = auth["client"].get(f"/api/ingest/batches/{bid}", headers=auth["headers"]).json()
    assert status["status"] == "completed" and status["stage"] == "done"
    assert status["file_status"][0]["status"] == "indexed"


def test_history_lists_documents_with_time_status_and_search_filters(auth, monkeypatch):
    _stub_pipeline(monkeypatch)
    ok, dup = f"ok-{auth['tag']}.txt", f"dup-{auth['tag']}.txt"
    body = f"Python engineer {auth['tag']}".encode()
    bid = _make_batch(auth["user_id"], [ok, dup])
    ing.process_batch(bid, [(ok, body), (dup, body)], auth["user_id"])  # second file is an exact duplicate

    c, h = auth["client"], auth["headers"]
    everything = c.get("/api/ingest/history?limit=200", headers=h).json()
    mine = [r for r in everything["items"] if auth["tag"] in (r["filename"] or "")]
    assert {r["filename"]: r["status"] for r in mine} == {ok: "indexed", dup: "duplicate"}
    assert all(r["uploaded_at"].endswith("Z") for r in mine)
    indexed = next(r for r in mine if r["status"] == "indexed")
    assert indexed["display_id"].startswith("TRU-CN-") and indexed["candidate_name"].startswith("Cand ")

    # status + search filters
    only_dups = c.get(f"/api/ingest/history?status=duplicate&q={auth['tag']}", headers=h).json()
    assert [r["filename"] for r in only_dups["items"]] == [dup]
    assert c.get("/api/ingest/history?status=bogus", headers=h).status_code == 400

    # time window: backdate our candidate and batch, then it must drop out of the 10-minute view
    db = SessionLocal()
    old = datetime.utcnow() - timedelta(hours=3)
    db.query(Candidate).filter(Candidate.original_filename == ok).update({"uploaded_at": old})
    db.query(IngestionBatch).filter(IngestionBatch.id == bid).update({"created_at": old})
    db.commit(); db.close()
    last_10 = c.get(f"/api/ingest/history?minutes=10&q={auth['tag']}", headers=h).json()
    assert last_10["items"] == []
    last_day = c.get(f"/api/ingest/history?minutes=1440&q={auth['tag']}", headers=h).json()
    assert len(last_day["items"]) == 2

    # requires login
    assert TestClient(app).get("/api/ingest/history").status_code == 401


def test_aggregate_endpoints_are_cached_and_invalidated_on_data_change(auth, monkeypatch):
    from backend.routers import analytics as analytics_module
    from backend.services.common.cache import clear_cache

    calls = []
    original = analytics_module._compute_overview
    monkeypatch.setattr(analytics_module, "_compute_overview", lambda *a, **k: calls.append(1) or original(*a, **k))
    c, h = auth["client"], auth["headers"]
    clear_cache("analytics:")
    c.get("/api/analytics/overview", headers=h); c.get("/api/analytics/overview", headers=h)
    assert len(calls) == 1, "second identical request must be served from cache"
    clear_cache("candidates:list:")  # any data write path calls this
    c.get("/api/analytics/overview", headers=h)
    assert len(calls) == 2, "a data change must invalidate the cached aggregate"
