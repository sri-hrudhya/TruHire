from test_location_role_filters import env
from backend.models import Position


def test_candidate_history_records_status_changes_without_resume_or_contact_data(env):
    candidate_id = env["make"]()
    response = env["client"].patch(
        f"/api/candidates/{candidate_id}/availability",
        headers=env["headers"], json={"status": "Not Active"},
    )

    assert response.status_code == 200
    history = env["client"].get(f"/api/candidates/{candidate_id}/history", headers=env["headers"])
    assert history.status_code == 200
    body = history.json()
    assert body["has_more"] is False
    assert body["items"][0]["event_type"] == "availability_status_changed"
    assert "Active to Not Active" in body["items"][0]["summary"]
    assert "email" not in body["items"][0]
    assert "resume_text" not in body["items"][0]


def test_candidate_history_shows_each_requirement_status_and_modifier(env):
    candidate_id = env["make"]()
    position_id = env["make_jd"]()
    position = env["db"].get(Position, position_id)
    position.client_name = "Ibridge"
    env["db"].commit()
    response = env["client"].put(
        f"/api/job-descriptions/{position_id}/candidates/{candidate_id}/status",
        headers=env["headers"], json={"status": "Interviewed"},
    )

    assert response.status_code == 200
    history = env["client"].get(f"/api/candidates/{candidate_id}/history", headers=env["headers"])
    requirement = history.json()["requirements"][0]
    assert requirement["client_name"] == "Ibridge"
    assert requirement["status"] == "Interviewed"
    assert requirement["modified_by"] == env["user"].name


def test_candidate_history_rejects_invalid_cursor(env):
    candidate_id = env["make"]()
    response = env["client"].get(f"/api/candidates/{candidate_id}/history?cursor=broken", headers=env["headers"])
    assert response.status_code == 422


def test_history_lists_requirements_for_the_directory_and_notes_for_availability(env):
    candidate_id = env["make"]()
    position_id = env["make_jd"]()
    position = env["db"].get(Position, position_id)
    position.client_name = "Aaseya"
    env["db"].commit()
    env["client"].put(f"/api/job-descriptions/{position_id}/candidates/{candidate_id}/status",
                      headers=env["headers"], json={"status": "Rejected"})

    listing = env["client"].get("/api/candidates", headers=env["headers"], params={"with_requirements": True}).json()
    row = next(item for item in listing["candidates"] if item["id"] == candidate_id)
    assert [(r["client_name"], r["status"]) for r in row["requirements"]] == [("Aaseya", "Rejected")]
    plain = env["client"].get("/api/candidates", headers=env["headers"]).json()
    assert "requirements" not in plain["candidates"][0]


def test_assistant_reports_open_positions_of_a_demand(env):
    position_id = env["make_jd"]()
    position = env["db"].get(Position, position_id)
    position.no_of_positions = 4
    env["db"].commit()
    body = env["client"].post("/api/assistant/message", headers=env["headers"],
                              json={"message": f"what is the number of open positions of {position.display_id}"}).json()
    assert body["action"] == "open_positions"
    assert "4 open positions" in body["reply"]


def test_assistant_shows_candidate_history_by_name(env):
    from backend.models import Candidate
    candidate_id = env["make"]()
    candidate = env["db"].get(Candidate, candidate_id)
    candidate.candidate_name = "Ravi Kumar"
    position_id = env["make_jd"]()
    env["db"].get(Position, position_id).client_name = "IBM"
    env["db"].commit()
    env["client"].put(f"/api/job-descriptions/{position_id}/candidates/{candidate_id}/status",
                      headers=env["headers"], json={"status": "Shortlisted"})

    body = env["client"].post("/api/assistant/message", headers=env["headers"],
                              json={"message": "show history of Ravi Kumar"}).json()
    assert body["action"] == "candidate_history"
    assert "IBM - Shortlisted" in body["reply"]
    assert body["requirements"][0]["client_name"] == "IBM"
    assert body["items"][0]["actor"]


def test_history_does_not_list_requirements_that_were_only_matched(env):
    from backend.models import CandidateMatch
    candidate_id = env["make"]()
    position_id = env["make_jd"]()
    env["db"].add(CandidateMatch(candidate_id=candidate_id, position_id=position_id, match_score=88.0))
    env["db"].commit()
    body = env["client"].get(f"/api/candidates/{candidate_id}/history", headers=env["headers"]).json()
    assert body["requirements"] == []
