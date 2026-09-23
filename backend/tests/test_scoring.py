from backend.services.scoring import (
    calculate_hybrid_score,
    compute_skill_overlap,
    extract_skills_from_jd
)


def test_skill_overlap_computation():
    cand_skills = ["Python", "FastAPI", "Docker", "Git"]
    target_skills = ["Python", "FastAPI", "Kubernetes", "AWS"]

    coverage, matched, missing = compute_skill_overlap(cand_skills, target_skills)
    assert coverage == 0.5  # 2 of 4 matched
    assert set(matched) == {"Python", "FastAPI"}
    assert set(missing) == {"Kubernetes", "AWS"}


def test_hybrid_scoring_exact_match():
    # Ideal candidate: high semantic, 100% skill match, sufficient exp, has degree
    score, breakdown = calculate_hybrid_score(
        semantic_sim=1.0,
        candidate_skills=["Python", "FastAPI", "Docker"],
        candidate_exp=6.0,
        candidate_edu="Bachelor of Science in Computer Science",
        jd_title="Senior Python Engineer",
        jd_text="Looking for a Senior Python Engineer with Bachelor degree and 5 years experience.",
        target_skills=["Python", "FastAPI", "Docker"],
        required_exp=5.0
    )

    assert score >= 95.0
    assert breakdown["semantic_score"] == 100.0
    assert breakdown["skill_score"] == 100.0
    assert breakdown["experience_penalty"] == 0.0
    assert breakdown["education_penalty"] == 0.0


def test_hybrid_scoring_with_experience_penalty():
    # Candidate has 2 years exp, job requires 5
    score, breakdown = calculate_hybrid_score(
        semantic_sim=0.8,
        candidate_skills=["Python"],
        candidate_exp=2.0,
        candidate_edu="B.S. Software Engineering",
        jd_title="Senior Python Engineer",
        jd_text="Requirements: 5 years experience in Python",
        target_skills=["Python"],
        required_exp=5.0
    )

    assert breakdown["experience_penalty"] > 0.0
    assert score <= 100.0


def test_extract_skills_from_jd():
    jd = "We are seeking a Backend Architect experienced in Python, Docker, Kubernetes, and PostgreSQL."
    skills = extract_skills_from_jd(jd)
    assert "Python" in skills
    assert "Docker" in skills
    assert "Kubernetes" in skills
    assert "PostgreSQL" in skills
