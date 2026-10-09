import uuid
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import User
from backend.auth import create_access_token, get_password_hash


def get_auth_token():
    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        user = User(email="recruiter@truhire.com", name="Test Recruiter", hashed_password=get_password_hash("pass123"))
        db.add(user)
        db.commit()
        db.refresh(user)
    token = create_access_token({"sub": user.id})
    db.close()
    return token


def test_requirement_display_id_and_creation():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a new Requirement
    payload = {
        "title": f"DevOps Platform Engineer {uuid.uuid4().hex[:6]}",
        "jd_text": "Looking for a Kubernetes, Terraform, AWS, and CI/CD specialist with 5+ years of experience."
    }
    create_resp = client.post("/api/job-descriptions", json=payload, headers=headers)
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()

    assert "id" in created
    assert "display_id" in created
    assert created["display_id"].startswith("TRU-JD-")
    assert len(created["display_id"]) == 11  # TRU-JD-0004 etc.
    req_id = created["id"]
    display_id = created["display_id"]

    # 2. Verify listing includes the display_id
    list_resp = client.get("/api/job-descriptions", headers=headers)
    assert list_resp.status_code == 200
    all_reqs = list_resp.json()
    matched = [r for r in all_reqs if r["id"] == req_id]
    assert len(matched) == 1
    assert matched[0]["display_id"] == display_id

    # 3. The legacy /api/positions mirror has been removed; /api/job-descriptions is canonical.
    assert client.get("/api/positions", headers=headers).status_code == 404

    # 4. Clean up requirement
    del_resp = client.delete(f"/api/job-descriptions/{req_id}", headers=headers)
    assert del_resp.status_code == 200


def test_candidate_display_ids_and_retrieval():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    candidates_resp = client.get("/api/candidates", headers=headers)
    assert candidates_resp.status_code == 200
    candidates = candidates_resp.json()["candidates"]
    assert len(candidates) > 0, "Expected existing candidates in database"

    for cand in candidates:
        assert "display_id" in cand
        assert cand["display_id"].startswith("TRU-CN-")
        assert len(cand["display_id"]) == 11


def _all_candidates(client, headers):
    resp = client.get("/api/candidates?limit=100", headers=headers)
    assert resp.status_code == 200
    return resp.json()


def test_requirement_matches_endpoint():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    list_resp = client.get("/api/job-descriptions", headers=headers)
    assert list_resp.status_code == 200
    reqs = list_resp.json()
    assert len(reqs) > 0

    first_req = reqs[0]
    matches_resp = client.get(f"/api/job-descriptions/{first_req['id']}/matches", headers=headers)
    assert matches_resp.status_code == 200
    matches_data = matches_resp.json()

    assert matches_data["position_id"] == first_req["id"]
    assert matches_data["display_id"] == first_req["display_id"]
    assert "position_title" in matches_data
    assert isinstance(matches_data["matches"], list)

    for m in matches_data["matches"]:
        cand = m["candidate"]
        assert cand["display_id"].startswith("TRU-CN-")
        assert "match_score" in m
        assert "llm_summary" in m
        # Each match must resolve to the same candidate record, and therefore the same resume
        detail = client.get(f"/api/candidates/{cand['id']}", headers=headers).json()
        assert detail["display_id"] == cand["display_id"]
        assert detail["resume_file_url"] == cand["resume_file_url"]


def test_requirement_matches_are_cached(monkeypatch):
    import backend.services.retrieval.search as search_module

    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/job-descriptions",
        json={"title": f"Cache Probe {uuid.uuid4().hex[:6]}", "jd_text": "Python, FastAPI and SQL engineer with 3+ years."},
        headers=headers,
    )
    assert create_resp.status_code == 200
    req_id = create_resp.json()["id"]

    calls = {"n": 0}
    original = search_module.execute_candidate_search

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(search_module, "execute_candidate_search", counting)
    try:
        first = client.get(f"/api/job-descriptions/{req_id}/matches", headers=headers)
        second = client.get(f"/api/job-descriptions/{req_id}/matches", headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert calls["n"] == 1, "Second request should be served from cache"

        # Editing the requirement text must invalidate the cached match results
        client.put(f"/api/job-descriptions/{req_id}", json={"jd_text": "Go and Kubernetes engineer."}, headers=headers)
        client.get(f"/api/job-descriptions/{req_id}/matches", headers=headers)
        assert calls["n"] == 2
    finally:
        client.delete(f"/api/job-descriptions/{req_id}", headers=headers)


def test_candidate_matches_refresh_after_scoring():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    candidates = _all_candidates(client, headers)["candidates"]
    assert candidates
    cand_id = candidates[0]["id"]
    # Prime the per-candidate match matrix cache
    client.get(f"/api/candidates/{cand_id}/matches", headers=headers)

    req = client.post(
        "/api/job-descriptions",
        json={"title": f"Matrix Probe {uuid.uuid4().hex[:6]}", "jd_text": "Generalist engineer, any stack."},
        headers=headers,
    ).json()
    try:
        scored = client.get(f"/api/job-descriptions/{req['id']}/matches?top_n=100", headers=headers).json()
        scored_ids = {m["candidate"]["id"] for m in scored["matches"]}
        if cand_id in scored_ids:
            matrix = client.get(f"/api/candidates/{cand_id}/matches", headers=headers).json()["matches"]
            assert any(m["position_id"] == req["id"] for m in matrix), "Stale cached match matrix"
    finally:
        client.delete(f"/api/job-descriptions/{req['id']}", headers=headers)


def test_requirement_deletion_safety():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    initial = _all_candidates(client, headers)
    initial_ids = {c["id"] for c in initial["candidates"]}

    create_resp = client.post(
        "/api/job-descriptions",
        json={"title": "Temporary Role to Test Deletion Safety", "jd_text": "Seeking an engineer to test requirement deletion without deleting candidates."},
        headers=headers,
    )
    assert create_resp.status_code == 200
    temp = create_resp.json()

    # Score candidates against it so CandidateMatch rows exist before removal
    client.get(f"/api/job-descriptions/{temp['id']}/matches", headers=headers)

    del_resp = client.delete(f"/api/job-descriptions/{temp['id']}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": 1, "id": temp["id"], "display_id": temp["display_id"]}

    assert client.get(f"/api/job-descriptions/{temp['id']}", headers=headers).status_code == 404
    listed_ids = {r["id"] for r in client.get("/api/job-descriptions", headers=headers).json()}
    assert temp["id"] not in listed_ids

    after = _all_candidates(client, headers)
    assert after["total"] == initial["total"]
    assert {c["id"] for c in after["candidates"]} == initial_ids

    # Candidate match matrices no longer reference the removed requirement
    for cid in list(initial_ids)[:5]:
        matches = client.get(f"/api/candidates/{cid}/matches", headers=headers).json()["matches"]
        assert all(m["position_id"] != temp["id"] for m in matches)


def test_requirement_ids_are_sequential_and_persistent():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    def create(n):
        r = client.post("/api/job-descriptions", json={"title": f"Seq {n}", "jd_text": "Sequential ID probe."}, headers=headers)
        assert r.status_code == 200
        return r.json()

    def num(item):
        return int(item["display_id"].split("-")[-1])

    a = create(1)
    b = create(2)
    try:
        assert num(b) == num(a) + 1
        # A fetched record keeps its ID; it is not regenerated per request
        assert client.get(f"/api/job-descriptions/{a['id']}", headers=headers).json()["display_id"] == a["display_id"]
        # Deleting the newest requirement must not free its number for reuse
        client.delete(f"/api/job-descriptions/{b['id']}", headers=headers)
        c = create(3)
        assert num(c) == num(b) + 1
        client.delete(f"/api/job-descriptions/{c['id']}", headers=headers)
    finally:
        client.delete(f"/api/job-descriptions/{a['id']}", headers=headers)
        client.delete(f"/api/job-descriptions/{b['id']}", headers=headers)


def test_candidate_caching_and_invalidation():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    candidates = _all_candidates(client, headers)["candidates"]
    assert candidates, "Expected existing candidates in database"
    cand = candidates[0]
    cand_id = cand["id"]
    orig_status = cand.get("status", "New")

    detail1 = client.get(f"/api/candidates/{cand_id}", headers=headers).json()
    assert detail1["id"] == cand_id
    assert detail1["display_id"] == cand["display_id"]

    new_status = "Interviewed" if orig_status != "Interviewed" else "Shortlisted"
    patch_resp = client.patch(f"/api/candidates/{cand_id}/status", json={"status": new_status}, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == new_status

    # Detail and list must both reflect the change, proving cache invalidation
    assert client.get(f"/api/candidates/{cand_id}", headers=headers).json()["status"] == new_status
    listed = {c["id"]: c for c in _all_candidates(client, headers)["candidates"]}
    assert listed[cand_id]["status"] == new_status

    client.patch(f"/api/candidates/{cand_id}/status", json={"status": orig_status}, headers=headers)


def test_email_rejects_empty_selection():
    client = TestClient(app)
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/email/send", json={"position_id": "any", "emails": []}, headers=headers)
    assert resp.status_code == 422
