from test_location_role_filters import env
from backend.models import Candidate, CandidateMatch, Position
from backend.services.candidates.tracker_fields import resume_fields


def _submit(env, status="Shortlisted", resume_text=None):
    candidate_id, position_id = env["make"](), env["make_jd"]()
    env["db"].get(Position, position_id).client_name = "Aaseya"
    cand = env["db"].get(Candidate, candidate_id)
    cand.phone, cand.extracted_skills, cand.years_experience = "9876543210", ["Camunda", "Java"], 6.0
    cand.resume_text = resume_text
    env["db"].commit()
    env["client"].put(f"/api/job-descriptions/{position_id}/candidates/{candidate_id}/status",
                      headers=env["headers"], json={"status": status})
    return candidate_id, position_id


def test_tracker_lists_only_status_set_candidates_with_autofill(env):
    candidate_id, position_id = _submit(env)
    other = env["make"]()
    env["db"].add(CandidateMatch(candidate_id=other, position_id=position_id, match_score=90.0))
    env["db"].commit()

    body = env["client"].get("/api/tracker", headers=env["headers"], params={"position_id": position_id}).json()
    assert [r["candidate_id"] for r in body["rows"]] == [candidate_id]
    values = body["rows"][0]["values"]
    assert values["primary_skill"] == "Camunda" and values["contact_no"] == "9876543210"
    assert values["interview_status"] == "Shortlisted" and values["recruiter"] == env["user"].name
    assert body["columns"][0]["label"] == "Primary Skill" and body["columns"][-1]["label"] == "Frameworks"
    by_client = env["client"].get("/api/tracker", headers=env["headers"], params={"client": " aaseya "}).json()
    assert candidate_id in [r["candidate_id"] for r in by_client["rows"]]


def test_tracker_fills_stated_resume_fields_and_cannot_be_edited(env):
    text = "Current CTC: 12 LPA\nExpected CTC: 16 LPA\nNotice Period: 30 days\nPreferred Location: Pune\nWorked on Banking projects with Spring Boot."
    candidate_id, position_id = _submit(env, resume_text=text)
    row = env["client"].get("/api/tracker", headers=env["headers"], params={"position_id": position_id}).json()["rows"][0]["values"]
    assert row["current_ctc"] == "12 LPA" and row["expected_ctc"] == "16 LPA" and row["preferred_location"] == "Pune"
    assert row["domains"] == "Banking" and "Spring Boot" in row["frameworks"]
    assert "lwd" not in row  # not stated in the resume: blank, never guessed
    assert env["client"].put(f"/api/tracker/{position_id}/{candidate_id}", headers=env["headers"], json={"data": {"current_ctc": "1"}}).status_code in (404, 405)


def test_resume_fields_blank_when_nothing_is_stated():
    assert resume_fields("Just a name and some skills", []) == {}
