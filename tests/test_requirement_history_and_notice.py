"""JD status / details, persistent requirement history, demand cards and editable notice period.

Real routers and database; classification and cache are the real code paths (JD text is chosen so the
keyword classifier needs no LLM).
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_access_token, get_password_hash
from backend.database import SessionLocal
from backend.main import app
from backend.models import Candidate, Position, RequirementHistory, User


@pytest.fixture
def ctx():
    db = SessionLocal()
    user = User(email=f"hist-{uuid.uuid4().hex[:6]}@truhire.test", name="History Tester", hashed_password=get_password_hash("pass123"))
    db.add(user)
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    created = []
    yield TestClient(app), headers, db, user, created
    for pid in created:
        db.query(RequirementHistory).filter(RequirementHistory.item_id == pid).delete(synchronize_session=False)
        db.query(Position).filter(Position.id == pid).delete(synchronize_session=False)
    db.query(RequirementHistory).filter(RequirementHistory.user_id == user.id).delete(synchronize_session=False)
    db.query(Position).filter(Position.created_by == user.id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    db.close()


def _create(client, headers, created, **extra):
    body = {"title": f"Java Developer {uuid.uuid4().hex[:5]}", "jd_text": "Java Spring Boot microservices developer with 5 years experience.", **extra}
    res = client.post("/api/job-descriptions", json=body, headers=headers)
    assert res.status_code == 200, res.text
    created.append(res.json()["id"])
    return res.json()


def _history(client, headers, item_id=None, **params):
    items = client.get("/api/requirement-history", params={"limit": 200, **params}, headers=headers).json()["items"]
    return [i for i in items if item_id is None or i["item_id"] == item_id]


def _listed(client, headers, jd_id):
    return next(j for j in client.get("/api/job-descriptions", headers=headers).json() if j["id"] == jd_id)


def test_create_defaults_to_open_and_persists_details(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, role="Backend Engineer", location="Pune", experience_years=5,
                 start_date="2026-11-01", end_date="2026-12-31")
    assert jd["status"] == "Open"
    assert (jd["role"], jd["location"], jd["experience_years"]) == ("Backend Engineer", "Pune", 5)
    listed = _listed(client, headers, jd["id"])
    assert listed["start_date"] == "2026-11-01" and listed["end_date"] == "2026-12-31"
    assert listed["created_by_name"] == "History Tester"


@pytest.mark.parametrize("bad", [
    {"status": "Draft"}, {"status": "On Hold"}, {"experience_years": -1}, {"experience_years": 99},
    {"start_date": "2026-12-31", "end_date": "2026-01-01"}, {"start_date": "not-a-date"},
    {"experience_years": 5, "experience_max_years": 3}, {"experience_max_years": 99},
])
def test_invalid_jd_details_rejected(ctx, bad):
    client, headers, db, user, created = ctx
    res = client.post("/api/job-descriptions", json={"title": "X", "jd_text": "Java developer", **bad}, headers=headers)
    assert res.status_code == 422


def test_update_rejects_end_before_existing_start_and_keeps_data(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, start_date="2026-11-01")
    res = client.put(f"/api/job-descriptions/{jd['id']}", json={"end_date": "2026-10-01"}, headers=headers)
    assert res.status_code == 422
    assert _listed(client, headers, jd["id"])["end_date"] is None


def test_several_locations_and_number_of_positions(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, locations=["Pune", " Mumbai ", "pune"], no_of_positions=4)
    assert jd["locations"] == ["Pune", "Mumbai"] and jd["location"] == "Pune; Mumbai" and jd["no_of_positions"] == 4
    listed = _listed(client, headers, jd["id"])
    assert listed["locations"] == ["Pune", "Mumbai"] and listed["no_of_positions"] == 4
    # Omitting the count on create means one position; locations can be replaced, cleared and recorded in history.
    plain = _create(client, headers, created)
    assert plain["no_of_positions"] == 1 and plain["locations"] == []
    res = client.put(f"/api/job-descriptions/{jd['id']}", json={"locations": ["Chennai"], "no_of_positions": 2}, headers=headers)
    assert res.json()["locations"] == ["Chennai"] and res.json()["location"] == "Chennai" and res.json()["no_of_positions"] == 2
    assert client.put(f"/api/job-descriptions/{jd['id']}", json={"locations": []}, headers=headers).json()["locations"] == []
    changes = [r["changes"] for r in _history(client, headers, jd["id"]) if r["action"] == "updated"]
    assert any("no_of_positions" in c for c in changes) and any("location" in c for c in changes)


def test_single_location_clients_still_work_and_bad_values_are_rejected(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, location="Pune")  # the older single-value field
    assert jd["locations"] == ["Pune"] and jd["location"] == "Pune"
    assert client.put(f"/api/job-descriptions/{jd['id']}", json={"location": "Mumbai"}, headers=headers).json()["locations"] == ["Mumbai"]
    for bad in ({"no_of_positions": 0}, {"no_of_positions": -2}, {"locations": ["x"] * 11}, {"locations": "Pune"}, {"locations": [1]}):
        res = client.post("/api/job-descriptions", json={"title": "X", "jd_text": "Java developer", **bad}, headers=headers)
        assert res.status_code == 422, bad


def test_chosen_folder_is_kept_and_can_be_changed_on_edit(ctx):
    from backend.models import canonical_demand_id
    client, headers, db, user, created = ctx
    genai, pega = canonical_demand_id("GenAI"), canonical_demand_id("Pega")
    jd = _create(client, headers, created, demand_id=genai)  # text is plain Java, but the recruiter chose GenAI
    assert jd["demand_id"] == genai
    # Editing the text does not re-classify the demand.
    res = client.put(f"/api/job-descriptions/{jd['id']}", json={"jd_text": "Java developer with Spring Boot and Hibernate"}, headers=headers)
    assert res.json()["demand_id"] == genai
    # Picking another folder moves it, and the move is recorded in history.
    res = client.put(f"/api/job-descriptions/{jd['id']}", json={"demand_id": pega}, headers=headers)
    assert res.status_code == 200 and res.json()["demand_id"] == pega
    assert any(r["changes"].get("demand", {}).get("new", "").endswith("Pega") for r in _history(client, headers, jd["id"]) if r["action"] == "updated")
    assert client.put(f"/api/job-descriptions/{jd['id']}", json={"demand_id": "nope"}, headers=headers).status_code == 422


def test_min_max_experience_persist_and_update_is_checked_against_stored_value(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, experience_years=3, experience_max_years=5)
    listed = _listed(client, headers, jd["id"])
    assert (listed["experience_years"], listed["experience_max_years"]) == (3, 5)
    res = client.put(f"/api/job-descriptions/{jd['id']}", json={"experience_max_years": 2}, headers=headers)
    assert res.status_code == 422
    assert _listed(client, headers, jd["id"])["experience_max_years"] == 5


def test_history_records_create_update_status_delete_newest_first(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, location="Pune")
    client.put(f"/api/job-descriptions/{jd['id']}", json={"location": "Mumbai", "experience_years": 4}, headers=headers)
    assert client.put(f"/api/job-descriptions/{jd['id']}/status", json={"status": "Fulfilled"}, headers=headers).json()["status"] == "Fulfilled"
    assert client.put(f"/api/job-descriptions/{jd['id']}/status", json={"status": "Draft"}, headers=headers).status_code == 400
    client.delete(f"/api/job-descriptions/{jd['id']}", headers=headers)

    rows = _history(client, headers, jd["id"])
    assert [r["action"] for r in rows] == ["deleted", "status_changed", "updated", "created"]
    assert all(r["user_name"] == "History Tester" and r["item_display_id"] == jd["display_id"] for r in rows)
    status, updated = rows[1], rows[2]
    assert status["changes"]["status"] == {"old": "Open", "new": "Fulfilled"}
    assert updated["changes"]["location"] == {"old": "Pune", "new": "Mumbai"}
    assert updated["changes"]["experience_years"] == {"old": None, "new": 4.0}
    assert all(r["demand_display_id"] == "TRU-DM-01" and r["demand_name"] == "Java" for r in rows)  # Demand ID travels with every entry
    stamps = [r["created_at"] for r in _history(client, headers)]
    assert stamps == sorted(stamps, reverse=True)


def test_noop_save_and_same_status_log_nothing(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created)
    client.put(f"/api/job-descriptions/{jd['id']}", json={"title": jd["title"]}, headers=headers)
    client.put(f"/api/job-descriptions/{jd['id']}/status", json={"status": "Open"}, headers=headers)
    assert [r["action"] for r in _history(client, headers, jd["id"])] == ["created"]


def test_status_change_through_update_is_logged_and_clearing_a_field_works(ctx):
    client, headers, db, user, created = ctx
    jd = _create(client, headers, created, role="Lead")
    client.put(f"/api/job-descriptions/{jd['id']}", json={"status": "Cancelled", "cancellation_reason": "On hold", "role": None}, headers=headers)
    acts = {r["action"]: r for r in _history(client, headers, jd["id"])}
    assert acts["status_changed"]["changes"]["status"]["new"] == "Cancelled"
    assert acts["status_changed"]["changes"]["cancellation_reason"]["new"] == "On hold"
    assert acts["updated"]["changes"]["role"] == {"old": "Lead", "new": None}


def test_history_filter_and_validation(ctx):
    client, headers, db, user, created = ctx
    _create(client, headers, created)
    assert all(r["action"] == "created" for r in _history(client, headers, action="created"))
    assert client.get("/api/requirement-history", params={"action": "bogus"}, headers=headers).status_code == 400
    assert client.get("/api/requirement-history").status_code in (401, 403)


def test_demands_expose_id_and_creator(ctx):
    client, headers, db, user, created = ctx
    demands = client.get("/api/demands", headers=headers).json()
    assert [d["name"] for d in demands] == ["Java", "GenAI", "Camunda", "Pega", "Others"]
    assert [d["display_id"] for d in demands] == [f"TRU-DM-0{i}" for i in range(1, 6)]
    assert all(d["created_at"] for d in demands)
    assert all(d["created_by_name"] is None for d in demands)  # seeded by the system: no creator shown


def test_meta_lists_only_the_five_jd_statuses(ctx):
    client, headers, *_ = ctx
    meta = client.get("/api/meta", headers=headers).json()
    assert meta["jd_statuses"] == ["Open", "Cancelled", "Fulfilled", "Mapped"]
    assert meta["notice_period_units"] == ["Days", "Weeks", "Months"]


def _candidate(db, user):
    c = Candidate(candidate_name="Notice Tester", extracted_skills=[], uploaded_by=user.id, uploaded_at=datetime.utcnow(),
                  file_hash=uuid.uuid4().hex, original_filename="n.pdf")
    db.add(c)
    db.commit()
    return c


def test_notice_period_edit_persist_clear_and_validate(ctx):
    client, headers, db, user, created = ctx
    cand = _candidate(db, user)
    try:
        url = f"/api/candidates/{cand.id}/notice-period"
        ok = client.patch(url, json={"value": 2, "unit": "Weeks"}, headers=headers)
        assert ok.status_code == 200 and ok.json()["notice_period_unit"] == "Weeks"
        got = client.get(f"/api/candidates/{cand.id}", headers=headers).json()
        assert (got["notice_period_value"], got["notice_period_unit"]) == (2, "Weeks")
        for bad in ({"value": -1, "unit": "Days"}, {"value": 1, "unit": "Years"}, {"value": 3}, {"unit": "Days"},
                    {"value": 100, "unit": "Months"}, {"value": "abc", "unit": "Days"}):
            assert client.patch(url, json=bad, headers=headers).status_code == 422, bad
        assert client.get(f"/api/candidates/{cand.id}", headers=headers).json()["notice_period_value"] == 2
        assert client.patch(url, json={"value": None, "unit": None}, headers=headers).status_code == 200
        assert client.get(f"/api/candidates/{cand.id}", headers=headers).json()["notice_period_value"] is None
        assert client.patch("/api/candidates/missing/notice-period", json={"value": 1, "unit": "Days"}, headers=headers).status_code == 404
    finally:
        db.delete(cand)
        db.commit()
