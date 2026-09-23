def test_create_and_version_bump_job_description(client, auth_headers):
    # 1. Create JD
    create_payload = {
        "title": "Senior AI Systems Engineer",
        "jd_text": "We need an AI engineer with strong Python, FastAPI, and OpenSearch expertise."
    }
    create_res = client.post("/api/job-descriptions", json=create_payload, headers=auth_headers)
    assert create_res.status_code == 200
    jd = create_res.json()
    jd_id = jd["id"]
    assert jd["jd_version"] == 1
    assert jd["title"] == "Senior AI Systems Engineer"

    # 2. Update title only: should NOT bump version
    update_title_res = client.put(f"/api/job-descriptions/{jd_id}", json={"title": "Staff AI Engineer"}, headers=auth_headers)
    assert update_title_res.status_code == 200
    assert update_title_res.json()["title"] == "Staff AI Engineer"
    assert update_title_res.json()["jd_version"] == 1

    # 3. Update text: MUST bump version to 2
    new_text = "Updated requirements: Must have 6+ years of Python, Docker, and Kubernetes expertise."
    update_text_res = client.put(f"/api/job-descriptions/{jd_id}", json={"jd_text": new_text}, headers=auth_headers)
    assert update_text_res.status_code == 200
    updated_jd = update_text_res.json()
    assert updated_jd["jd_version"] == 2
    assert updated_jd["jd_text"] == new_text


def test_summarize_job_description(client, auth_headers):
    create_payload = {
        "title": "Full-Stack React Engineer",
        "jd_text": "Responsibilities: Build beautiful UIs using React, Vite, and Tailwind. Requirements: 3+ years experience with modern JavaScript."
    }
    create_res = client.post("/api/job-descriptions", json=create_payload, headers=auth_headers)
    jd_id = create_res.json()["id"]

    # Call summarize
    sum_res = client.post(f"/api/job-descriptions/{jd_id}/summarize", headers=auth_headers)
    assert sum_res.status_code == 200
    data = sum_res.json()
    assert "jd_summary" in data
    assert len(data["jd_summary"]) > 20
