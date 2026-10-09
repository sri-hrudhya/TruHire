"""Requirement match threshold: score scale, boundary, missing scores, per-requirement filtering,
and the index-coverage regression (resumes missing from Qdrant/OpenSearch are never scored).

Retrieval backends, embeddings, Laya and the LLM are stubbed; scoring formulas, routers and
the DB are the real code.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import backend.routers.ingestion as ingestion
import backend.services.retrieval.search as search_module
from backend.auth import create_access_token, get_password_hash
from backend.config import settings
from backend.database import SessionLocal
from backend.main import app
from backend.models import Candidate, CandidateMatch, IngestionBatch, RequirementCandidateStatus, User
from backend.routers.job_descriptions import meets_match_threshold
from backend.services.common.cache import clear_cache
from backend.services.retrieval.scoring import calculate_hybrid_score


def _clear_caches():
    for prefix in ("candidates:list:", "candidate:", "requirements:", "search:", "jd_skills:", "decision:"):
        clear_cache(prefix)


# --- Threshold predicate -------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (49.9, False), (49.99, False), (50.0, True), (50, True), (50.1, True), (85.0, True), (100.0, True),
    (None, False), (float("nan"), False), ("75", False), (True, False),
])
def test_threshold_boundary_and_missing_scores(score, expected):
    assert meets_match_threshold(score, 50.0) is expected


def test_threshold_is_percentage_scale():
    assert settings.REQUIREMENT_MATCH_THRESHOLD == 50.0
    # A 0-1 fraction is not silently rescaled: the engine never emits that format.
    assert meets_match_threshold(0.85, settings.REQUIREMENT_MATCH_THRESHOLD) is False


# --- Original scoring formula is unchanged and emits 0-100 ---------------------------

def test_hybrid_score_formula_and_scale_unchanged():
    score, breakdown = calculate_hybrid_score(
        semantic_sim=0.5, candidate_skills=["Python", "Go"], candidate_exp=5.0, candidate_edu="BSc University",
        jd_title="Engineer", jd_text="Python Go Rust Java engineer", target_skills=["Python", "Go", "Rust", "Java"],
        required_exp=3.0,
    )
    # 0.45*0.5 + 0.35*0.5 + 0.20 = 0.60 -> 60.0 on the percentage scale.
    assert score == 60.0 and breakdown["final_score"] == 60.0
    assert breakdown["semantic_score"] == 50.0 and breakdown["skill_score"] == 50.0

    exact, _ = calculate_hybrid_score(
        semantic_sim=0.0, candidate_skills=["A", "B", "C"], candidate_exp=5.0, candidate_edu="BSc University",
        jd_title="x", jd_text="x", target_skills=["A", "B", "C", "D", "E", "F"], required_exp=3.0,
    )
    # 0.35*0.5 + 0.20 = 0.375 -> 37.5
    assert exact == 37.5


# --- Fixtures --------------------------------------------------------------------------

@pytest.fixture
def env():
    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        user = User(email="recruiter@truhire.com", name="Test Recruiter", hashed_password=get_password_hash("pass123"))
        db.add(user)
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    client = TestClient(app)
    tag = uuid.uuid4().hex[:6]
    created_cands, created_jds = [], []

    def make_cands(n, indexed=True, skills=None):
        out = []
        for i in range(n):
            c = Candidate(
                display_id=f"THR-{tag}-{len(created_cands)}", candidate_name=f"Thr{len(created_cands)} {tag}",
                email=f"thr{len(created_cands)}.{tag}@example.com", extracted_skills=skills or ["Python"],
                years_experience=5, education="BSc University", resume_text="Python engineer", status="New",
                uploaded_by=user.id, uploaded_at=datetime.utcnow(), file_hash=f"thr-{tag}-{len(created_cands)}",
                original_filename="thr.pdf",
            )
            db.add(c)
            db.flush()
            if indexed:
                c.qdrant_point_id = c.id
                c.opensearch_doc_id = c.id
            created_cands.append(c)
            out.append(c)
        db.commit()
        return [c.id for c in out]

    def make_jd(title="Python Engineer"):
        r = client.post("/api/job-descriptions", headers=headers, json={"title": f"{title} {tag}", "jd_text": "Python engineer with FastAPI."})
        assert r.status_code == 200, r.text
        created_jds.append(r.json()["id"])
        return r.json()["id"]

    _clear_caches()
    yield {"db": db, "client": client, "headers": headers, "make_cands": make_cands, "make_jd": make_jd, "tag": tag}

    for jid in created_jds:
        client.delete(f"/api/job-descriptions/{jid}", headers=headers)
    ids = [c.id for c in created_cands]
    db.query(CandidateMatch).filter(CandidateMatch.candidate_id.in_(ids)).delete(synchronize_session=False)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.candidate_id.in_(ids)).delete(synchronize_session=False)
    db.query(Candidate).filter(Candidate.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    db.close()
    _clear_caches()


def _fake_search(scores_by_position):
    """Stand-in for execute_candidate_search returning fixed scores per requirement."""
    def fake(db_, query_text="", filter_skills=None, min_experience=None, position_id=None, top_n=20):
        rows = scores_by_position[position_id]
        cands = {c.id: c for c in db_.query(Candidate).filter(Candidate.id.in_([cid for cid, _ in rows])).all()}
        return {"total_matches": len(rows), "retrieval": {"vector": True, "lexical": True, "hybrid": True}, "results": [
            {"candidate": search_module._candidate_payload(cands[cid]), "match_score": s, "score_breakdown": {},
             "llm_summary": "", "cited_quote": "", "cited_section": ""}
            for cid, s in rows
        ]}
    return fake


# --- Requirement endpoint --------------------------------------------------------------

def test_requirement_filtering_boundaries_missing_and_statuses(env, monkeypatch):
    ids = env["make_cands"](5)
    jd = env["make_jd"]()
    scores = [(ids[0], 72.4), (ids[1], 50.0), (ids[2], 49.9), (ids[3], None), (ids[4], 12.0)]
    monkeypatch.setattr(search_module, "execute_candidate_search", _fake_search({jd: scores}))

    # A "Not Shortlisted" status must not hide a qualifying candidate.
    r = env["client"].put(f"/api/job-descriptions/{jd}/candidates/{ids[1]}/status", json={"status": "Not Shortlisted"}, headers=env["headers"])
    assert r.status_code == 200

    data = env["client"].get(f"/api/job-descriptions/{jd}/matches", headers=env["headers"]).json()
    assert [(m["candidate"]["id"], m["match_score"]) for m in data["matches"]] == [(ids[0], 72.4), (ids[1], 50.0)]
    assert {m["candidate"]["id"]: m["requirement_status"] for m in data["matches"]}[ids[1]] == "Not Shortlisted"
    assert data["total_scored"] == 5 and data["total_matches"] == 2 and data["min_match_score"] == 50.0


def test_threshold_is_applied_per_requirement(env, monkeypatch):
    a, b = env["make_cands"](2)
    jd1, jd2 = env["make_jd"]("Role One"), env["make_jd"]("Role Two")
    monkeypatch.setattr(search_module, "execute_candidate_search", _fake_search({
        jd1: [(a, 80.0), (b, 30.0)],
        jd2: [(b, 65.0), (a, 45.0)],
    }))
    get = lambda jd: [m["candidate"]["id"] for m in env["client"].get(f"/api/job-descriptions/{jd}/matches", headers=env["headers"]).json()["matches"]]
    assert get(jd1) == [a]
    assert get(jd2) == [b]


# --- Real search path: stored score == API score, unindexed resumes are not scored ------

@pytest.fixture
def stub_retrieval(monkeypatch):
    """Real execute_candidate_search; only external services are stubbed."""
    pool = {"vector": []}
    monkeypatch.setattr(search_module, "generate_embedding", lambda text: [0.1, 0.2])
    monkeypatch.setattr(search_module, "search_vectors", lambda vec, k: list(pool["vector"]))
    monkeypatch.setattr(search_module, "search_lexical", lambda *a, **k: [])
    monkeypatch.setattr(search_module, "extract_skills_from_jd", lambda text: ["Python", "FastAPI"])
    monkeypatch.setattr(search_module.decision, "rerank_scores_batch", lambda items: [(s, None) for s, _, _ in items])
    monkeypatch.setattr(search_module, "generate_match_summary", lambda *a, **k: ("summary", "", "Requirements"))
    monkeypatch.setattr(search_module, "check_search_result", lambda *a, **k: type("G", (), {"passed": True})())
    return pool


def test_stored_and_returned_scores_share_one_percentage_field(env, stub_retrieval):
    strong, weak = env["make_cands"](1, skills=["Python", "FastAPI"]) + env["make_cands"](1, skills=["Excel"])
    stub_retrieval["vector"] = [{"candidate_id": strong, "score": 0.9}, {"candidate_id": weak, "score": 0.2}]
    jd = env["make_jd"]()

    data = env["client"].get(f"/api/job-descriptions/{jd}/matches", headers=env["headers"]).json()
    shown = {m["candidate"]["id"]: m["match_score"] for m in data["matches"]}
    # strong: retrieval 0.6*0.9=0.54 -> 0.45*0.54 + 0.35*1.0 + 0.20 = 0.793 -> 79.3
    assert shown == {strong: 79.3}
    assert data["retrieval"]["vector"] is True and data["retrieval"]["lexical"] is False

    db = SessionLocal()
    stored = {m.candidate_id: m.match_score for m in db.query(CandidateMatch).filter(CandidateMatch.position_id == jd).all()}
    db.close()
    assert stored[strong] == 79.3 and 1.0 < stored[weak] < 50.0  # both scored, only one qualifies


def test_unindexed_resumes_are_reported_not_silently_dropped(env, stub_retrieval):
    indexed = env["make_cands"](1, skills=["Python", "FastAPI"])[0]
    missing = env["make_cands"](1, indexed=False, skills=["Python", "FastAPI"])[0]
    stub_retrieval["vector"] = [{"candidate_id": indexed, "score": 0.9}]
    jd = env["make_jd"]()

    data = env["client"].get(f"/api/job-descriptions/{jd}/matches", headers=env["headers"]).json()
    assert [m["candidate"]["id"] for m in data["matches"]] == [indexed]
    assert missing not in {m["candidate"]["id"] for m in data["matches"]}
    assert data["unindexed_candidates"] >= 1


# --- Ingestion: failed indexing must not mark a candidate as indexed ------------------

def test_failed_batch_indexing_leaves_candidates_reindexable(env, monkeypatch):
    db = env["db"]
    user = db.query(User).first()
    batch = IngestionBatch(created_by=user.id, total_files=1, status="processing")
    db.add(batch)
    db.commit()
    tag = env["tag"]
    monkeypatch.setattr(ingestion, "save_upload_file", lambda name, data: (f"/tmp/{name}", None))
    monkeypatch.setattr(ingestion, "extract_text_from_file", lambda name, data: "Python engineer")
    monkeypatch.setattr(ingestion, "parse_resume", lambda text, name: {"candidate_name": f"Batch {tag}", "email": None, "phone": None,
                                                                      "extracted_skills": ["Python"], "years_experience": 2.0, "education": None})
    monkeypatch.setattr(ingestion, "detect_pii", lambda text: {})
    monkeypatch.setattr(ingestion, "generate_embeddings_batch", lambda texts: [[0.1] for _ in texts])

    def qdrant_down(items):
        raise ConnectionError("Qdrant unreachable")
    monkeypatch.setattr(ingestion, "upsert_candidates_batch", qdrant_down)

    ingestion.process_batch(batch.id, [(f"batch-{tag}.pdf", f"unique-bytes-{tag}".encode())], user.id)

    check = SessionLocal()
    try:
        cand = check.query(Candidate).filter(Candidate.ingestion_batch_id == batch.id).one()
        assert cand.qdrant_point_id is None and cand.opensearch_doc_id is None
        assert check.get(IngestionBatch, batch.id).status == "failed"
    finally:
        check.query(Candidate).filter(Candidate.ingestion_batch_id == batch.id).delete(synchronize_session=False)
        check.query(IngestionBatch).filter(IngestionBatch.id == batch.id).delete(synchronize_session=False)
        check.commit()
        check.close()


# --- Search is requirement-only -------------------------------------------------------

def test_search_requires_a_requirement(env):
    client, headers = env["client"], env["headers"]
    assert client.post("/api/search", json={"query": "python"}, headers=headers).status_code == 422
    assert client.post("/api/search", json={"query": "python", "position_id": ""}, headers=headers).status_code == 422
    assert client.post("/api/search", json={"query": "python", "position_id": "no-such-id"}, headers=headers).status_code == 404
    db = SessionLocal()
    try:
        with pytest.raises(search_module.RequirementRequired):
            search_module.execute_candidate_search(db, query_text="python")
    finally:
        db.close()


def test_saved_search_without_requirement_is_not_restored(env):
    from backend.models import SearchState
    db = SessionLocal()
    user = db.query(User).first()
    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    snapshot = {k: getattr(state, k) for k in ("position_id", "results")} if state else None
    if not state:
        state = SearchState(user_id=user.id)
        db.add(state)
    state.position_id = None
    state.results = [{"match_score": 30.0}]
    db.commit()
    try:
        assert env["client"].get("/api/search/state", headers=env["headers"]).json() == {"state": None}
    finally:
        if snapshot is None:
            db.delete(state)
        else:
            for k, v in snapshot.items():
                setattr(state, k, v)
        db.commit()
        db.close()


def test_query_and_skill_chips_narrow_within_requirement(env, stub_retrieval):
    a = env["make_cands"](1, skills=["Python", "FastAPI"])[0]
    b = env["make_cands"](1, skills=["Python"])[0]
    stub_retrieval["vector"] = [{"candidate_id": a, "score": 0.9}, {"candidate_id": b, "score": 0.9}]
    jd = env["make_jd"]()
    db = SessionLocal()
    try:
        everyone = search_module.execute_candidate_search(db, query_text="", position_id=jd, top_n=50)
        narrowed = search_module.execute_candidate_search(db, query_text="api", filter_skills=["FastAPI"], position_id=jd, top_n=50)
    finally:
        db.close()
    assert {r["candidate"]["id"] for r in everyone["results"]} == {a, b}
    assert [r["candidate"]["id"] for r in narrowed["results"]] == [a]
    # Scores are always the requirement-based hybrid score (0-100), never a flat placeholder.
    assert all(0 < r["match_score"] <= 100 for r in everyone["results"])
    assert everyone["scored_against_jd"]["id"] == jd
