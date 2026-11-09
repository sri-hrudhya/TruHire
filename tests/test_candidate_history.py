from test_location_role_filters import env
from backend.models import Position


def test_candidate_history_records_status_changes_without_resume_or_contact_data(env):
    candidate_id = env["make"]()
    response = env["client"].patch(
        f"/api/candidates/{candidate_id}/status",
        headers=env["headers"], json={"status": "Not Active"},
    )

    assert response.status_code == 200
    history = env["client"].get(f"/api/candidates/{candidate_id}/history", headers=env["headers"])
    assert history.status_code == 200
    body = history.json()
    assert body["has_more"] is False
    assert body["items"][0]["event_type"] == "candidate_status_changed"
    assert "Not Active" in body["items"][0]["summary"]
    assert body["current_status"]["status"] == "Not Active"
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
        headers=env["headers"], json={"status": "Interview in Progress"},
    )

    assert response.status_code == 200
    history = env["client"].get(f"/api/candidates/{candidate_id}/history", headers=env["headers"])
    requirement = history.json()["requirements"][0]
    assert requirement["client_name"] == "Ibridge"
    assert requirement["status"] == "Interview in Progress"
    assert requirement["modified_by"] == env["user"].name


def test_candidate_history_rejects_invalid_cursor(env):
    candidate_id = env["make"]()
    response = env["client"].get(f"/api/candidates/{candidate_id}/history?cursor=broken", headers=env["headers"])
    assert response.status_code == 422
