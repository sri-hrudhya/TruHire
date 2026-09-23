import io
from backend.models import Candidate, IngestionBatch


def test_bulk_resume_upload_and_duplicate_skip(client, auth_headers, db_session):
    # Resume 1
    resume_content_1 = b"""Sarah Connor
sarah@skynet-resistance.io | 415-555-0101
Skills: Python, FastAPI, Docker, Security
5 years of experience in distributed security systems.
Bachelor of Science in Computer Science.
"""
    # Resume 2
    resume_content_2 = b"""Kyle Reese
kyle@resistance.org | 415-555-0102
Skills: Linux, C++, DevOps, Docker
4 years of experience in system infrastructure.
"""

    files = [
        ("files", ("sarah_connor.txt", io.BytesIO(resume_content_1), "text/plain")),
        ("files", ("kyle_reese.txt", io.BytesIO(resume_content_2), "text/plain"))
    ]

    response = client.post("/api/ingest/upload", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    batch_id = data["batch_id"]
    assert data["total_files"] == 2

    # Check batch status
    batch_res = client.get(f"/api/ingest/batches/{batch_id}", headers=auth_headers)
    assert batch_res.status_code == 200
    batch_data = batch_res.json()
    assert batch_data["processed_count"] == 2
    assert batch_data["duplicate_count"] == 0

    # Verify candidates are in shared pool (position_id is None)
    cands = db_session.query(Candidate).all()
    assert len(cands) == 2
    for c in cands:
        assert c.position_id is None

    # Now upload the EXACT same file 1 again -> must be detected as duplicate!
    duplicate_file = [
        ("files", ("sarah_connor_copy.txt", io.BytesIO(resume_content_1), "text/plain"))
    ]
    dup_response = client.post("/api/ingest/upload", files=duplicate_file, headers=auth_headers)
    dup_batch_id = dup_response.json()["batch_id"]

    dup_batch_res = client.get(f"/api/ingest/batches/{dup_batch_id}", headers=auth_headers)
    dup_data = dup_batch_res.json()
    assert dup_data["duplicate_count"] == 1
    assert dup_data["processed_count"] == 0
    assert len(dup_data["error_log"]) == 1
    assert "duplicate" in dup_data["error_log"][0]["error"].lower()
