from backend.models import Candidate, Position, CandidateMatch, IngestionBatch


def test_analytics_aggregations_and_funnel(client, auth_headers, db_session, test_user):
    # Seed candidates with varying experience, skills, and statuses
    candidates_data = [
        ("C1", ["Python", "FastAPI"], 1.5, "New"),
        ("C2", ["Python", "Docker"], 3.5, "Shortlisted"),
        ("C3", ["React", "TypeScript"], 6.0, "Interviewed"),
        ("C4", ["Python", "Kubernetes"], 8.0, "Rejected"),
    ]

    for name, skills, exp, status in candidates_data:
        c = Candidate(
            candidate_name=name,
            email=f"{name.lower()}@test.com",
            extracted_skills=skills,
            years_experience=exp,
            status=status,
            uploaded_by=test_user.id,
            file_hash=f"hash_{name}",
            original_filename=f"{name}.txt"
        )
        db_session.add(c)

    db_session.commit()

    res = client.get("/api/analytics/overview", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    # 1. Summary counts
    assert data["summary"]["total_candidates"] == 4

    # 2. Experience distribution
    exp_dist = data["experience_distribution"]
    assert exp_dist["0-2 years"] == 1
    assert exp_dist["3-5 years"] == 1
    assert exp_dist["5+ years"] == 2

    # 3. Status funnel
    funnel = data["status_funnel"]
    assert funnel["New"] == 1
    assert funnel["Shortlisted"] == 1
    assert funnel["Interviewed"] == 1
    assert funnel["Rejected"] == 1

    # 4. Top skills
    top_skills = {item["skill"]: item["count"] for item in data["top_skills"]}
    assert top_skills["Python"] == 3
    assert top_skills["FastAPI"] == 1

    # 5. Non-negotiable constraint: verify no candidate objects are in the response
    assert "candidates" not in data
    assert "candidate_list" not in data
