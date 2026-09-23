from backend.services.search import parse_search_query
from backend.models import Candidate, Position, CandidateMatch


def test_search_query_modifiers():
    # Append modifiers
    skills, exp, _, mode = parse_search_query("Python and Docker", existing_skills=["FastAPI"])
    assert mode == "append"
    assert "FastAPI" in skills
    assert "Python" in skills
    assert "Docker" in skills

    # Replace modifiers
    skills, exp, _, mode = parse_search_query("only React", existing_skills=["Python", "FastAPI"])
    assert mode == "replace"
    assert "React" in skills
    assert "Python" not in skills

    # Experience extraction
    _, exp, _, _ = parse_search_query("Need 5+ years experience in Python")
    assert exp == 5.0


def test_search_top_n_pagination_and_total_count(client, auth_headers, db_session, test_user):
    # Seed 25 candidates
    for i in range(25):
        c = Candidate(
            candidate_name=f"Candidate {i}",
            email=f"candidate_{i}@example.com",
            extracted_skills=["Python", "FastAPI"] if i % 2 == 0 else ["React", "CSS"],
            years_experience=float(i % 8 + 1),
            uploaded_by=test_user.id,
            file_hash=f"hash_{i}",
            original_filename=f"cand_{i}.txt"
        )
        db_session.add(c)
    db_session.commit()

    # Search with default top_n=20
    search_payload = {
        "query": "Python",
        "top_n": 10
    }
    res = client.post("/api/search", json=search_payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["top_n"] == 10
    assert len(data["results"]) == 10
    # Total matches should reflect all matching candidates (13 have Python)
    assert data["total_matches"] == 13


def test_search_scored_against_jd(client, auth_headers, db_session, test_user):
    # Seed Candidate
    cand = Candidate(
        candidate_name="Ada Lovelace",
        email="ada@algorithm.org",
        extracted_skills=["Python", "Algorithms", "Mathematics"],
        years_experience=7.0,
        education="Master of Mathematics",
        uploaded_by=test_user.id,
        file_hash="hash_ada",
        original_filename="ada.txt"
    )
    db_session.add(cand)

    # Seed Job Description
    pos = Position(
        title="Senior Algorithm Engineer",
        jd_text="Required: 5+ years Python, Algorithms. Degree required.",
        jd_version=1,
        created_by=test_user.id
    )
    db_session.add(pos)
    db_session.commit()

    # Search candidates with position_id selected
    payload = {
        "query": "",
        "position_id": pos.id,
        "top_n": 10
    }
    res = client.post("/api/search", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["scored_against_jd"]["id"] == pos.id
    assert len(data["results"]) == 1
    first_res = data["results"][0]
    assert first_res["match_score"] >= 75.0
    assert "semantic_score" in first_res["score_breakdown"]
    assert "skill_score" in first_res["score_breakdown"]

    # Verify CandidateMatch was persisted in DB
    match_row = db_session.query(CandidateMatch).filter(
        CandidateMatch.candidate_id == cand.id,
        CandidateMatch.position_id == pos.id
    ).first()
    assert match_row is not None
    assert match_row.match_score == first_res["match_score"]
