"""Requirements threshold, per-requirement statuses, AI-personalized email and email history.

The scorer, LLM and SMTP server are stubbed so these tests are deterministic; everything
else (routers, DB models, caching, delivery service) is the real code path.
"""
import json
import re
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import backend.routers.search as search_router
import backend.services.common.email_delivery as delivery
import backend.services.llm.ai_service as ai_service
import backend.services.retrieval.search as search_module
from backend.auth import create_access_token, get_password_hash
from backend.config import settings
from backend.database import SessionLocal
from backend.main import app
from backend.models import Candidate, EmailRecord, RequirementCandidateStatus, SearchState, User

SCORES = [85.0, 50.0, 49.9, 20.0]


@pytest.fixture
def ctx(monkeypatch):
    db = SessionLocal()
    user = db.query(User).first()
    if not user:
        user = User(email="recruiter@truhire.com", name="Test Recruiter", hashed_password=get_password_hash("pass123"))
        db.add(user)
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    client = TestClient(app)

    tag = uuid.uuid4().hex[:6]
    skills = [["Kubernetes", "Terraform"], ["Python", "FastAPI"], ["Go"], ["Excel"]]
    cands = []
    for i, score in enumerate(SCORES):
        c = Candidate(
            display_id=f"TST-{tag}-{i}", candidate_name=f"Probe{i} {tag}", email=f"probe{i}.{tag}@example.com",
            extracted_skills=skills[i], years_experience=3 + i, education="BSc Computer Science",
            resume_text=f"Probe{i} built platform tooling with {', '.join(skills[i])} at a fintech.",
            status="New", uploaded_by=user.id, uploaded_at=datetime.utcnow(), file_hash=f"tst-{tag}-{i}",
            original_filename=f"probe{i}.pdf",
        )
        db.add(c)
        cands.append(c)
    db.commit()
    cand_ids = [c.id for c in cands]

    def fake_search(db_, query_text="", filter_skills=None, min_experience=None, position_id=None, top_n=20):
        rows = db_.query(Candidate).filter(Candidate.id.in_(cand_ids)).all()
        by_id = {c.id: c for c in rows}
        return {"total_matches": len(SCORES), "results": [
            {"candidate": search_module._candidate_payload(by_id[cid]), "match_score": s,
             "score_breakdown": {"matched_skills": by_id[cid].extracted_skills}, "llm_summary": "", "cited_quote": "", "cited_section": ""}
            for cid, s in zip(cand_ids, SCORES)
        ]}

    monkeypatch.setattr(search_module, "execute_candidate_search", fake_search)

    prompts = []

    def fake_llm(messages, **kwargs):
        prompt = messages[-1]["content"]
        prompts.append(prompt)
        name = re.search(r"^Name: (.+)$", prompt, re.M).group(1)
        role = re.search(r"^ROLE TITLE: (.+)$", prompt, re.M).group(1)
        skills_line = re.search(r"^Skills: (.+)$", prompt, re.M).group(1)
        return json.dumps({"subject": f"{role}: a conversation, {name.split()[0]}?",
                           "body": f"Hi {name.split()[0]},\n\nYour work with {skills_line} stood out for our {role} opening. Reply to set up a call."})

    monkeypatch.setattr(ai_service, "chat_completion", fake_llm)
    monkeypatch.setattr(settings, "SMTP_HOST", None)

    jd_ids = []

    def make_jd(title="Platform Engineer"):
        r = client.post("/api/job-descriptions", headers=headers,
                        json={"title": f"{title} {tag}", "jd_text": "Kubernetes, Terraform and Python platform engineer."})
        assert r.status_code == 200, r.text
        jd_ids.append(r.json()["id"])
        return r.json()

    yield {"client": client, "headers": headers, "cands": cand_ids, "make_jd": make_jd, "prompts": prompts, "user": user}

    for jid in jd_ids:
        client.delete(f"/api/job-descriptions/{jid}", headers=headers)
    db.query(EmailRecord).filter(EmailRecord.candidate_id.in_(cand_ids)).delete(synchronize_session=False)
    db.query(RequirementCandidateStatus).filter(RequirementCandidateStatus.candidate_id.in_(cand_ids)).delete(synchronize_session=False)
    db.query(Candidate).filter(Candidate.id.in_(cand_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()
    from backend.services.common.cache import clear_cache
    for prefix in ("candidates:list:", "candidate:", "requirements:", "search:", "email:"):
        clear_cache(prefix)


def _shortlist(ctx, jd_id, cid, status="Shortlisted"):
    r = ctx["client"].put(f"/api/job-descriptions/{jd_id}/candidates/{cid}/status", json={"status": status}, headers=ctx["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_requirement_shows_only_candidates_at_or_above_50(ctx):
    jd = ctx["make_jd"]()
    data = ctx["client"].get(f"/api/job-descriptions/{jd['id']}/matches", headers=ctx["headers"]).json()
    scores = [m["match_score"] for m in data["matches"]]
    assert scores == [85.0, 50.0]
    assert data["min_match_score"] == 50.0
    assert data["total_matches"] == 2 and data["total_scored"] == 4
    assert all(m["requirement_status"] == "Pending Review" for m in data["matches"])
    assert all(m["candidate"]["display_id"] and m["candidate"]["email"] for m in data["matches"])

    # Lower-scoring candidates are hidden, not deleted.
    db = SessionLocal()
    assert db.query(Candidate).filter(Candidate.id.in_(ctx["cands"])).count() == 4
    db.close()


def test_search_results_are_not_filtered(ctx, monkeypatch):
    monkeypatch.setattr(search_router, "execute_candidate_search", search_module.execute_candidate_search)
    db = SessionLocal()
    saved = db.query(SearchState).filter(SearchState.user_id == ctx["user"].id).first()
    snapshot = {k: getattr(saved, k) for k in ("query", "filter_skills", "min_experience", "position_id", "top_n", "results", "total_matches", "retrieval")} if saved else None
    try:
        jd = ctx["make_jd"]()
        r = ctx["client"].post("/api/search", json={"query": "platform", "position_id": jd["id"]}, headers=ctx["headers"])
        assert r.status_code == 200, r.text
        # Search lists every scored candidate for the requirement, including those below 50%.
        assert [x["match_score"] for x in r.json()["results"]] == SCORES
    finally:
        state = db.query(SearchState).filter(SearchState.user_id == ctx["user"].id).first()
        if snapshot is None and state:
            db.delete(state)
        elif state:
            for k, v in snapshot.items():
                setattr(state, k, v)
        db.commit()
        db.close()


def test_statuses_are_specific_to_each_requirement(ctx):
    jd1, jd2 = ctx["make_jd"]("Role A"), ctx["make_jd"]("Role B")
    top = ctx["cands"][0]
    _shortlist(ctx, jd1["id"], top)
    _shortlist(ctx, jd2["id"], top, "Not Shortlisted")

    def status(jd_id):
        ms = ctx["client"].get(f"/api/job-descriptions/{jd_id}/matches", headers=ctx["headers"]).json()["matches"]
        return {m["candidate"]["id"]: m["requirement_status"] for m in ms}[top]

    assert status(jd1["id"]) == "Shortlisted"
    assert status(jd2["id"]) == "Not Shortlisted"
    # Served from the scoring cache, yet the status update is still reflected.
    _shortlist(ctx, jd1["id"], top, "Pending Review")
    assert status(jd1["id"]) == "Pending Review"

    bad = ctx["client"].put(f"/api/job-descriptions/{jd1['id']}/candidates/{top}/status", json={"status": "Interviewed"}, headers=ctx["headers"])
    assert bad.status_code == 400


def test_ai_generation_is_personalized_and_requires_shortlist(ctx):
    jd = ctx["make_jd"]()
    c0, c1 = ctx["cands"][0], ctx["cands"][1]
    _shortlist(ctx, jd["id"], c0)
    _shortlist(ctx, jd["id"], c1)

    r = ctx["client"].post("/api/email/generate", json={"position_id": jd["id"], "candidate_ids": [c0, c1, ctx["cands"][2]]}, headers=ctx["headers"])
    assert r.status_code == 200, r.text
    out = r.json()
    drafts = {d["candidate_id"]: d for d in out["drafts"]}
    assert set(drafts) == {c0, c1}
    assert drafts[c0]["subject"] != drafts[c1]["subject"]
    assert drafts[c0]["body"] != drafts[c1]["body"]
    assert "Kubernetes" in drafts[c0]["body"] and "FastAPI" in drafts[c1]["body"]
    assert jd["title"] in drafts[c0]["subject"]
    assert [e["candidate_id"] for e in out["errors"]] == [ctx["cands"][2]]  # not shortlisted

    # The prompt carried the real JD and the candidate's own resume text.
    assert any("Kubernetes, Terraform and Python platform engineer." in p and "Probe0" in p for p in ctx["prompts"])


@pytest.mark.parametrize("llm_failure", ["raise", "unreachable", "garbage", "empty", "placeholder"])
def test_ai_generation_failure_is_reported_without_fallback(ctx, monkeypatch, llm_failure):
    jd = ctx["make_jd"]()
    c0 = ctx["cands"][0]
    _shortlist(ctx, jd["id"], c0)

    def broken(messages, **kwargs):
        if llm_failure == "raise":
            raise RuntimeError("DGX vLLM chat request timed out.")
        if llm_failure == "garbage":
            return "not json"
        if llm_failure == "empty":
            return json.dumps({"subject": "", "body": ""})
        return json.dumps({"subject": "Hello", "body": "Hi [Candidate Name], join [Company Name]."})

    if llm_failure == "unreachable":
        # Real provider client against a closed port: exercises the actual connection-failure path.
        from backend.services.llm import vllm
        monkeypatch.setattr(ai_service, "chat_completion", vllm.chat_completion)
        monkeypatch.setattr(settings, "VLLM_BASE_URL", "http://127.0.0.1:9/v1")
        monkeypatch.setattr(settings, "VLLM_MODEL", "unavailable-model")
        monkeypatch.setattr(settings, "VLLM_TIMEOUT", 3.0)
    else:
        monkeypatch.setattr(ai_service, "chat_completion", broken)
    resp = ctx["client"].post("/api/email/generate", json={"position_id": jd["id"], "candidate_ids": [c0]}, headers=ctx["headers"])
    assert resp.status_code == 200
    out = resp.json()
    # No draft of any kind is returned: the UI shows the error with a retry instead of a template.
    assert out["drafts"] == []
    assert out["errors"][0]["candidate_id"] == c0 and out["errors"][0]["retryable"] is True
    assert out["errors"][0]["reason"]

    # Nothing can be sent or recorded as a result of the failed generation.
    db = SessionLocal()
    assert db.query(EmailRecord).filter(EmailRecord.candidate_id == c0).count() == 0
    db.close()

    # Retrying once the provider recovers yields a real personalized draft.
    monkeypatch.undo()
    monkeypatch.setattr(ai_service, "chat_completion", lambda messages, **kw: json.dumps(
        {"subject": f"Re: {jd['title']}", "body": f"Hi Probe0, about the {jd['title']} role."}))
    retry = ctx["client"].post("/api/email/generate", json={"position_id": jd["id"], "candidate_ids": [c0]}, headers=ctx["headers"]).json()
    assert retry["errors"] == [] and retry["drafts"][0]["subject"] == f"Re: {jd['title']}"


def test_send_history_duplicates_and_simulation(ctx):
    client, headers = ctx["client"], ctx["headers"]
    jd = ctx["make_jd"]()
    c0, c1 = ctx["cands"][0], ctx["cands"][1]
    _shortlist(ctx, jd["id"], c0)
    _shortlist(ctx, jd["id"], c1)

    # Recruiter-edited content is what gets sent and stored.
    key = uuid.uuid4().hex
    payload = {"position_id": jd["id"], "emails": [
        {"candidate_id": c0, "subject": "Edited subject A", "body": "Edited body A", "idempotency_key": key},
        {"candidate_id": c1, "subject": "Edited subject B", "body": "Edited body B", "idempotency_key": uuid.uuid4().hex},
    ]}
    sent = client.post("/api/email/send", json=payload, headers=headers).json()
    assert sent["delivery_mode"] == "simulated"
    assert sent["simulated_count"] == 2 and sent["sent_count"] == 0
    assert {r["status"] for r in sent["results"]} == {"simulated"}

    # Same idempotency key (double click) -> no second email.
    again = client.post("/api/email/send", json={"position_id": jd["id"], "emails": [payload["emails"][0]]}, headers=headers).json()
    assert again["results"][0]["duplicate"] is True and again["simulated_count"] == 0

    # New draft for an already-emailed candidate needs explicit confirmation.
    fresh = {"candidate_id": c0, "subject": "Follow-up", "body": "Second note", "idempotency_key": uuid.uuid4().hex}
    blocked = client.post("/api/email/send", json={"position_id": jd["id"], "emails": [fresh]}, headers=headers).json()
    assert blocked["results"] == [] and blocked["skipped"][0]["already_emailed"] is True
    allowed = client.post("/api/email/send", json={"position_id": jd["id"], "emails": [fresh], "allow_resend": True}, headers=headers).json()
    assert allowed["simulated_count"] == 1

    # Not-shortlisted candidates are never emailed.
    rejected = client.post("/api/email/send", headers=headers, json={"position_id": jd["id"], "emails": [
        {"candidate_id": ctx["cands"][2], "subject": "x", "body": "y"}]}).json()
    assert rejected["results"] == [] and "not Shortlisted" in rejected["skipped"][0]["reason"]

    roles = {r["position_id"]: r for r in client.get("/api/email/history", headers=headers).json()["roles"]}
    role = roles[jd["id"]]
    assert role["total_emails"] == 3 and role["position_display_id"] == jd["display_id"] and role["position_title"] == jd["title"]
    assert role["latest_at"]

    records = client.get(f"/api/email/history/{jd['id']}", headers=headers).json()["records"]
    assert len(records) == 3
    rec = next(r for r in records if r["subject"] == "Edited subject A")
    assert rec["body"] == "Edited body A" and rec["candidate_id"] == c0 and rec["recipient_email"].startswith("probe0.")
    assert client.get(f"/api/email/records/{rec['id']}", headers=headers).json()["body"] == "Edited body A"

    # Requirements view reflects the email activity for the same requirement.
    ms = client.get(f"/api/job-descriptions/{jd['id']}/matches", headers=headers).json()["matches"]
    assert {m["candidate"]["id"]: m["last_email"]["status"] for m in ms if m["last_email"]}[c0] == "simulated"

    # History survives requirement deletion.
    client.delete(f"/api/job-descriptions/{jd['id']}", headers=headers)
    roles = {r["position_id"]: r for r in client.get("/api/email/history", headers=headers).json()["roles"]}
    assert roles[jd["id"]]["requirement_deleted"] is True and roles[jd["id"]]["position_title"] == jd["title"]


def test_smtp_failure_then_retry(ctx, monkeypatch):
    client, headers = ctx["client"], ctx["headers"]
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_FROM", "talent@example.com")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    outbox, fail = [], {"on": True}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg):
            if fail["on"]:
                raise ConnectionRefusedError("SMTP server refused connection")
            outbox.append(msg)

    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    assert client.get("/api/email/config", headers=headers).json()["delivery_mode"] == "smtp"

    jd = ctx["make_jd"]()
    c0 = ctx["cands"][0]
    _shortlist(ctx, jd["id"], c0)
    res = client.post("/api/email/send", headers=headers, json={"position_id": jd["id"], "emails": [
        {"candidate_id": c0, "subject": "Real subject", "body": "Real body", "idempotency_key": uuid.uuid4().hex}]}).json()
    assert res["failed_count"] == 1 and res["sent_count"] == 0
    record = res["results"][0]
    assert record["status"] == "failed" and "refused" in record["error"]

    # A failed email does not count as already-emailed history; the retry endpoint resends it.
    fail["on"] = False
    retried = client.post(f"/api/email/records/{record['id']}/retry", headers=headers).json()
    assert retried["status"] == "sent" and retried["attempts"] == 2 and retried["error"] is None
    assert len(outbox) == 1 and outbox[0]["To"] == record["recipient_email"] and outbox[0]["Subject"] == "Real subject"
    assert client.post(f"/api/email/records/{record['id']}/retry", headers=headers).status_code == 409

    hist = client.get(f"/api/email/history/{jd['id']}", headers=headers).json()["records"]
    assert [r["status"] for r in hist] == ["sent"]
