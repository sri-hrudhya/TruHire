import io


def test_full_end_to_end_recruitment_flow(client):
    # 1. Register recruiter
    reg_res = client.post("/api/auth/register", json={
        "email": "lead.recruiter@truhire.io",
        "name": "Elena Rostova",
        "password": "SecurePassword2026!"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Bulk upload resumes
    c1 = b"""Maya Lin
maya.lin@domain.com | 555-123-4567
Skills: Python, FastAPI, Docker, PostgreSQL, Machine Learning
6 years of experience building machine learning backend microservices.
Master of Science in Computer Science.
"""
    c2 = b"""James Wilson
j.wilson@domain.com | 555-987-6543
Skills: React, TypeScript, Next.js, CSS, HTML
4 years of frontend UI engineering experience.
Bachelor of Arts in Interactive Media.
"""
    upload_res = client.post(
        "/api/ingest/upload",
        files=[
            ("files", ("maya_lin.txt", io.BytesIO(c1), "text/plain")),
            ("files", ("james_wilson.txt", io.BytesIO(c2), "text/plain"))
        ],
        headers=headers
    )
    assert upload_res.status_code == 200
    batch_id = upload_res.json()["batch_id"]

    # Check batch status
    batch_status_res = client.get(f"/api/ingest/batches/{batch_id}", headers=headers)
    assert batch_status_res.status_code == 200
    assert batch_status_res.json()["processed_count"] == 2

    # 3. Create Job Description
    jd_res = client.post(
        "/api/job-descriptions",
        json={
            "title": "Lead Python ML Platform Engineer",
            "jd_text": "We are seeking a Lead Engineer with 5+ years of experience in Python, FastAPI, Docker, and Machine Learning. M.S. degree preferred."
        },
        headers=headers
    )
    assert jd_res.status_code == 200
    jd_id = jd_res.json()["id"]
    assert jd_res.json()["jd_version"] == 1

    # 4. Summarize Job Description
    sum_res = client.post(f"/api/job-descriptions/{jd_id}/summarize", headers=headers)
    assert sum_res.status_code == 200
    assert "jd_summary" in sum_res.json()

    # 5. Search candidates and score against the JD
    search_res = client.post(
        "/api/search",
        json={
            "query": "Python and Machine Learning",
            "position_id": jd_id,
            "top_n": 10
        },
        headers=headers
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total_matches"] >= 1
    assert len(search_data["results"]) >= 1

    top_candidate = search_data["results"][0]["candidate"]
    assert top_candidate["candidate_name"] == "Maya Lin"
    assert search_data["results"][0]["match_score"] >= 80.0
    cand_id = top_candidate["id"]

    # 6. Update candidate status to Shortlisted
    status_res = client.patch(
        f"/api/candidates/{cand_id}/status",
        json={"status": "Shortlisted"},
        headers=headers
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "Shortlisted"

    # 7. Check cross-JD match matrix on candidate detail
    matrix_res = client.get(f"/api/candidates/{cand_id}/matches", headers=headers)
    assert matrix_res.status_code == 200
    assert matrix_res.json()["total_matched_positions"] >= 1

    # 8. Query analytics overview
    analytics_res = client.get("/api/analytics/overview", headers=headers)
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.json()
    assert analytics_data["summary"]["total_candidates"] == 2
    assert analytics_data["status_funnel"]["Shortlisted"] == 1

    # 9. RAG Chat Q&A
    chat_res = client.post(
        "/api/chat",
        json={
            "candidate_id": cand_id,
            "messages": [{"role": "user", "content": "What is this candidate's main technical expertise?"}]
        },
        headers=headers
    )
    assert chat_res.status_code == 200
    assert "reply" in chat_res.json()

    # 10. Export candidates to CSV
    export_res = client.get("/api/export/candidates?format=csv", headers=headers)
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "Maya Lin" in export_res.text
