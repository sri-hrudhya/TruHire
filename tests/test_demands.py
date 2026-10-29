import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.database import SessionLocal, engine, ensure_schema, _seed_default_demands
from backend.models import User, Position, Candidate, CandidateMatch, canonical_demand_id
from backend.auth import create_access_token, get_password_hash
from backend.services.classification import classify_jd, classify_jd_detailed

client = TestClient(app)
CATEGORIES = ["Java", "GenAI", "Camunda", "Pega", "Others"]

JAVA_JD = "Senior Java Developer. Build Spring Boot microservices with Hibernate and JPA on the JVM. Maven, JUnit."
GENAI_JD = "GenAI Engineer. Build LLM applications: RAG pipelines, LangChain, prompt engineering, embeddings and vector databases."
CAMUNDA_JD = "Camunda Developer. Model BPMN and DMN processes on Camunda 8 (Zeebe) and integrate workers."
PEGA_JD = "Pega Developer. Certified Pega CSSA building case management on Pega Infinity (PRPC)."
OTHER_JD = "Accountant. Manage month-end close, accounts payable and financial reporting."


def _headers():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(email="recruiter@truhire.com", name="Test Recruiter", hashed_password=get_password_hash("pass123"))
            db.add(user)
            db.commit()
            db.refresh(user)
        return {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    finally:
        db.close()


def _category_of(jd, h):
    demands = {d["id"]: d["name"] for d in client.get("/api/demands", headers=h).json()}
    return demands[client.get(f"/api/job-descriptions/{jd['id']}", headers=h).json()["demand_id"]]


@pytest.fixture
def made():
    h = _headers()
    ids = []

    def make(title, body, **extra):
        r = client.post("/api/job-descriptions", json={"title": title, "jd_text": body, **extra}, headers=h)
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
        return r.json()

    yield h, make
    for i in ids:
        client.delete(f"/api/job-descriptions/{i}", headers=h)


# --- seeding / fixed categories --------------------------------------------------------

def _demand_rows():
    with engine.connect() as c:
        return c.execute(text("SELECT id, name FROM demands")).fetchall()


def test_exactly_five_categories_seeded_and_unique_after_repeated_startups():
    for _ in range(3):
        ensure_schema()
    rows = _demand_rows()
    assert sorted(n for _, n in rows) == sorted(CATEGORIES)
    assert sorted(i for i, _ in rows) == sorted(canonical_demand_id(n) for n in CATEGORIES)
    listed = client.get("/api/demands", headers=_headers()).json()
    assert [d["name"] for d in listed] == CATEGORIES and all(d["is_default"] for d in listed)


def test_demand_create_update_delete_are_blocked():
    h = _headers()
    assert client.post("/api/demands", json={"name": "Platform"}, headers=h).status_code == 403
    assert client.post("/api/demands", json={"name": "java"}, headers=h).status_code == 403
    assert client.post("/api/demands", json={}, headers=h).status_code == 422
    java = canonical_demand_id("Java")
    assert client.put(f"/api/demands/{java}", json={"name": "Renamed"}, headers=h).status_code == 400
    assert client.delete(f"/api/demands/{java}?detach_jds=true", headers=h).status_code == 400
    assert client.put("/api/demands/missing", json={"name": "a"}, headers=h).status_code == 404
    assert client.delete("/api/demands/missing", headers=h).status_code == 404
    assert client.get("/api/demands").status_code in (401, 403)
    assert len(_demand_rows()) == 5


# --- classification --------------------------------------------------------------------

@pytest.mark.parametrize("title,body,expected", [
    ("Backend Engineer", JAVA_JD, "Java"),
    ("AI Engineer", GENAI_JD, "GenAI"),
    ("Workflow Developer", CAMUNDA_JD, "Camunda"),
    ("Platform Developer", PEGA_JD, "Pega"),
    ("Finance Associate", OTHER_JD, "Others"),
    ("JavaScript Developer", "React, Node and JavaScript front-end work.", "Others"),
    ("QA Engineer", "Manual testing. Familiarity with Java is a plus.", "Others"),  # one passing mention
    ("", "", "Others"),
])
def test_classification_of_representative_jds(title, body, expected):
    assert classify_jd(title, body) == expected


def test_tie_break_priority_is_deterministic():
    # Equal scores: Camunda > Pega > GenAI > Java.
    assert classify_jd("", "camunda camunda pega pega") == "Camunda"
    assert classify_jd("", "pega pega java java") == "Pega"
    assert classify_jd("", "llm llm java java") == "GenAI"
    # A higher score beats priority.
    assert classify_jd("", "Java Spring Boot Hibernate JPA J2EE developer with camunda exposure") == "Java"


def test_classification_uses_content_not_the_title_or_file_name():
    # A misleading "java" title does not outvote a body that is clearly Pega.
    assert classify_jd("java", PEGA_JD + " Pega PRPC Pega CSSA Pega.") == "Pega"
    # A neutral title with Camunda content is still Camunda.
    assert classify_jd("resume 1", CAMUNDA_JD) == "Camunda"
    res = classify_jd_detailed("x", OTHER_JD)
    assert res.category == "Others" and not res.confident and res.note


# --- create / upload / edit ------------------------------------------------------------

def test_create_path_auto_categorises_unless_a_folder_is_chosen(made):
    h, make = made
    for title, body, expected in [("a", JAVA_JD, "Java"), ("b", GENAI_JD, "GenAI"), ("c", CAMUNDA_JD, "Camunda"),
                                  ("d", PEGA_JD, "Pega"), ("e", OTHER_JD, "Others")]:
        jd = make(f"{title} {uuid.uuid4().hex[:5]}", body)
        assert jd["demand_id"] == canonical_demand_id(expected) and _category_of(jd, h) == expected
    # A folder the recruiter chose wins over classification.
    jd = make("forced", JAVA_JD, demand_id=canonical_demand_id("Pega"))
    assert jd["demand_id"] == canonical_demand_id("Pega")
    assert make("vague", OTHER_JD)["classification_note"]


def test_upload_path_classifies_from_extracted_document_text(made):
    h, make = made
    r = client.post("/api/job-descriptions/extract-text", headers=h,
                    files={"file": ("java_developer.txt", PEGA_JD.encode(), "text/plain")})  # filename says Java, content says Pega
    assert r.status_code == 200, r.text
    ex = r.json()
    assert ex["category"] == "Pega"
    jd = make(ex["title"], ex["jd_text"], file_url=ex["file_url"], original_filename=ex["original_filename"])
    assert _category_of(jd, h) == "Pega" and jd["original_filename"] == "java_developer.txt"


def test_editing_content_keeps_folder_and_identity(made):
    h, make = made
    jd = make(f"Edit {uuid.uuid4().hex[:5]}", JAVA_JD)
    assert _category_of(jd, h) == "Java"
    r = client.put(f"/api/job-descriptions/{jd['id']}", json={"jd_text": CAMUNDA_JD}, headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == jd["id"] and r.json()["jd_version"] == 2 and _category_of(jd, h) == "Java"
    # Only choosing another folder moves it.
    r = client.put(f"/api/job-descriptions/{jd['id']}", json={"demand_id": canonical_demand_id("Camunda")}, headers=h)
    assert _category_of(jd, h) == "Camunda"
    # A non-content edit leaves the category alone.
    client.put(f"/api/job-descriptions/{jd['id']}/demand", json={"demand_id": canonical_demand_id("Pega")}, headers=h)
    client.put(f"/api/job-descriptions/{jd['id']}", json={"original_filename": "x.txt"}, headers=h)
    assert _category_of(jd, h) == "Pega"


def test_demand_endpoint_validates_and_null_reclassifies(made):
    h, make = made
    jd = make(f"Re {uuid.uuid4().hex[:5]}", GENAI_JD)
    assert client.put(f"/api/job-descriptions/{jd['id']}/demand", json={"demand_id": "nope"}, headers=h).status_code == 404
    assert client.put("/api/job-descriptions/missing/demand", json={"demand_id": None}, headers=h).status_code == 404
    client.put(f"/api/job-descriptions/{jd['id']}/demand", json={"demand_id": canonical_demand_id("Java")}, headers=h)
    r = client.put(f"/api/job-descriptions/{jd['id']}/demand", json={"demand_id": None}, headers=h)
    assert r.status_code == 200 and r.json()["demand_id"] == canonical_demand_id("GenAI") and r.json()["jd_version"] == 1


def test_category_jd_listing_and_counts(made):
    h, make = made
    before = {d["name"]: d["jd_count"] for d in client.get("/api/demands", headers=h).json()}
    jd = make(f"Count {uuid.uuid4().hex[:5]}", PEGA_JD)
    after = {d["name"]: d["jd_count"] for d in client.get("/api/demands", headers=h).json()}
    assert after["Pega"] == before["Pega"] + 1 and after["Java"] == before["Java"]
    pega = canonical_demand_id("Pega")
    assert jd["id"] in [j["id"] for j in client.get(f"/api/demands/{pega}/job-descriptions", headers=h).json()]
    assert client.get("/api/demands/missing-id", headers=h).status_code == 404
    # The list the Search selector filters on: every JD sits under one of the five categories.
    rows = client.get("/api/job-descriptions", headers=h).json()
    assert all(r["demand_id"] in {canonical_demand_id(n) for n in CATEGORIES} for r in rows)


# --- migration -------------------------------------------------------------------------

def test_migration_maps_legacy_categories_and_preserves_data():
    tag = uuid.uuid4().hex[:6]
    legacy = {"java": f"legacy-java-{tag}", "pega": f"legacy-pega-{tag}", "other": f"legacy-other-{tag}", "nodemand": None}
    with engine.begin() as c:
        c.execute(text("INSERT INTO demands (id, name, created_by, created_at) VALUES (:i, '  JAVA ', NULL, now())"), {"i": legacy["java"]})
        c.execute(text("INSERT INTO demands (id, name, created_by, created_at) VALUES (:i, 'pEga', NULL, now())"), {"i": legacy["pega"]})
        c.execute(text("INSERT INTO demands (id, name, created_by, created_at) VALUES (:i, 'Platform Hiring', NULL, now())"), {"i": legacy["other"]})
    db = SessionLocal()
    uid = db.query(User).first().id
    cand = Candidate(candidate_name=f"Mig {tag}", email=f"mig{tag}@example.com", extracted_skills=["Java"], years_experience=3,
                     education="BSc", resume_text="Java", status="New", uploaded_by=uid, file_hash=f"mig-{tag}", original_filename="m.pdf")
    db.add(cand)
    db.flush()
    pos = {}
    for key, demand_id, body in (("java", legacy["java"], OTHER_JD), ("pega", legacy["pega"], OTHER_JD), ("other", legacy["other"], JAVA_JD),
                                 ("nodemand", None, CAMUNDA_JD)):
        p = Position(title=f"Mig {key} {tag}", jd_text=body, created_by=uid, jd_version=3, demand_id=demand_id)
        db.add(p)
        db.flush()
        pos[key] = p.id
    db.add(CandidateMatch(candidate_id=cand.id, position_id=pos["other"], match_score=77.0, jd_version=3))
    db.commit()
    cand_id = cand.id
    db.close()
    try:
        for _ in range(2):  # idempotent
            ensure_schema()
        assert sorted(n for _, n in _demand_rows()) == sorted(CATEGORIES)
        db = SessionLocal()
        try:
            got = {k: db.query(Position).filter(Position.id == v).one() for k, v in pos.items()}
            assert got["java"].demand_id == canonical_demand_id("Java")          # name matched despite case/whitespace
            assert got["pega"].demand_id == canonical_demand_id("Pega")
            assert got["other"].demand_id == canonical_demand_id("Others")       # unknown legacy category -> Others
            assert got["nodemand"].demand_id == canonical_demand_id("Camunda")   # uncategorised JD classified by content
            assert all(p.jd_version == 3 for p in got.values())
            m = db.query(CandidateMatch).filter(CandidateMatch.position_id == pos["other"]).one()
            assert m.match_score == 77.0 and m.candidate_id == cand_id
        finally:
            db.close()
    finally:
        db = SessionLocal()
        db.query(CandidateMatch).filter(CandidateMatch.position_id.in_(pos.values())).delete(synchronize_session=False)
        db.query(Position).filter(Position.id.in_(pos.values())).delete(synchronize_session=False)
        db.query(Candidate).filter(Candidate.id == cand_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_seeding_twice_in_one_transaction_is_stable():
    with engine.begin() as c:
        _seed_default_demands(c)
        _seed_default_demands(c)
    assert len(_demand_rows()) == 5


# --- search passes through unchanged ---------------------------------------------------

def test_search_modes_pass_through_unchanged(monkeypatch, made):
    h, make = made
    jd = make(f"Srch {uuid.uuid4().hex[:5]}", JAVA_JD)
    calls = []

    def fake_search(db, query_text="", skills=None, min_exp=None, position_id=None, top_n=20, location=None, role=None, demand_id=None, **kw):
        calls.append({"query": query_text, "position_id": position_id})
        return {"results": [], "total_matches": 0, "retrieval": {}}

    monkeypatch.setattr("backend.routers.search.execute_candidate_search", fake_search)
    assert client.post("/api/search", json={"position_id": jd["id"], "top_n": 10}, headers=h).status_code == 200
    assert client.post("/api/search", json={"query": "spring boot", "top_n": 10}, headers=h).status_code == 200  # category + keyword => no JD id
    assert client.post("/api/search", json={"query": "python"}, headers=h).status_code == 200
    assert [c["position_id"] for c in calls] == [jd["id"], None, None]
    monkeypatch.undo()
    # A category id is not a JD.
    assert client.post("/api/search", json={"position_id": canonical_demand_id("Java")}, headers=h).status_code == 404
