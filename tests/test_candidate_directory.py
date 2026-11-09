from test_location_role_filters import env
from backend.models import Candidate
from backend.services.ingestion.parsing import heuristic_parse_resume


def test_directory_search_matches_name_email_phone_and_current_company(env):
    candidate_id = env["make"]()
    candidate = env["db"].get(Candidate, candidate_id)
    candidate.candidate_name = "Ravi Kumar"
    candidate.email = "ravi.kumar@example.test"
    candidate.email_norm = candidate.email.casefold()
    candidate.phone = "+1 (415) 555-0137"
    candidate.phone_norm = "14155550137"
    candidate.current_company = "Ibridge Systems"
    env["db"].commit()

    for query in ("Ravi Kumar", "ravi.kumar@example.test", "5550137", "Ibridge"):
        response = env["client"].get("/api/candidates", headers=env["headers"], params={"q": query})
        assert response.status_code == 200
        assert candidate_id in [item["id"] for item in response.json()["candidates"]], query


def test_assistant_candidate_lookup_understands_plain_language_and_returns_near_matches(env):
    candidate_id = env["make"]()
    candidate = env["db"].get(Candidate, candidate_id)
    candidate.candidate_name = "Ravi Kumar"
    candidate.email = "ravi.kumar@example.test"
    candidate.email_norm = candidate.email.casefold()
    candidate.current_company = "Ibridge Systems"
    env["db"].commit()

    response = env["client"].post("/api/assistant/message", headers=env["headers"], json={
        "message": "candidate search current company Ibridge"
    })

    assert response.status_code == 200
    assert response.json()["action"] == "candidate_lookup"
    assert candidate_id in [item["id"] for item in response.json()["results"]]


def test_resume_parser_extracts_only_an_explicit_current_company_label():
    parsed = heuristic_parse_resume("Ravi Kumar\nCurrent Company: Ibridge Systems\nSenior Engineer", "ravi.txt")
    assert parsed["current_company"] == "Ibridge Systems"
    unstated = heuristic_parse_resume("Ravi Kumar\nWorked at OldCo from 2018 to 2020", "ravi.txt")
    assert unstated["current_company"] == ""
