import os
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db, SessionLocal
from backend.models import User, Candidate, IngestionBatch
from backend.auth import get_current_user
from backend.services.storage import save_upload_file, compute_file_hash
from backend.services.parsing import extract_text_from_file, heuristic_parse_resume
from backend.services.pii import redact_pii
from backend.services.ai_service import generate_embedding
from backend.services.opensearch import index_candidate

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def process_single_file(
    file_bytes: bytes,
    original_filename: str,
    batch_id: str,
    user_id: str,
    db: Session
):
    """
    Processes a single resume file:
    1. Compute SHA-256 hash to detect duplicate.
    2. Parse resume text and fields.
    3. Redact PII before embedding.
    4. Generate vector embedding.
    5. Save candidate to DB (shared pool, position_id is None).
    6. Index in OpenSearch / vector store.
    """
    file_hash = compute_file_hash(file_bytes)

    # Check for duplicate file hash in database
    existing = db.query(Candidate).filter(Candidate.file_hash == file_hash).first()
    if existing:
        return "duplicate", f"Skipped exact duplicate of candidate '{existing.candidate_name}' (ID: {existing.id})"

    # Save to disk
    file_url, _ = save_upload_file(original_filename, file_bytes)

    # Extract text
    raw_text = extract_text_from_file(original_filename, file_bytes)
    if not raw_text.strip():
        return "failed", f"Failed to extract readable text from '{original_filename}'"

    # Parse resume structure
    parsed = heuristic_parse_resume(raw_text, original_filename)

    # Redact PII before embedding
    safe_profile_text = (
        f"Candidate: {parsed['candidate_name']}\n"
        f"Skills: {', '.join(parsed['extracted_skills'])}\n"
        f"Experience: {parsed['years_experience']} years\n"
        f"Education: {parsed['education']}\n"
        f"Content: {raw_text[:2000]}"
    )
    redacted_text = redact_pii(safe_profile_text, candidate_name=parsed["candidate_name"])

    # Generate embedding
    vector = generate_embedding(redacted_text)

    # Create Candidate record in shared pool
    candidate = Candidate(
        position_id=None,
        resume_file_url=file_url,
        candidate_name=parsed["candidate_name"],
        email=parsed["email"],
        phone=parsed["phone"],
        extracted_skills=parsed["extracted_skills"],
        years_experience=parsed["years_experience"],
        education=parsed["education"],
        status="New",
        uploaded_by=user_id,
        uploaded_at=datetime.utcnow(),
        ingestion_batch_id=batch_id,
        file_hash=file_hash,
        original_filename=original_filename
    )
    db.add(candidate)
    db.flush()

    # Index in OpenSearch
    doc_id = index_candidate(
        candidate_id=candidate.id,
        vector=vector,
        metadata={
            "candidate_name": candidate.candidate_name,
            "skills": candidate.extracted_skills,
            "years_experience": candidate.years_experience
        }
    )
    candidate.opensearch_doc_id = doc_id
    db.commit()

    return "processed", None


def run_batch_ingestion_task(batch_id: str, files_data: List[tuple], user_id: str):
    """
    Background worker for batch ingestion.
    files_data is a list of tuples: (original_filename, file_bytes)
    """
    db = SessionLocal()
    try:
        batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
        if not batch:
            return

        processed = 0
        failed = 0
        duplicates = 0
        errors = []

        for filename, file_bytes in files_data:
            try:
                outcome, detail = process_single_file(file_bytes, filename, batch_id, user_id, db)
                if outcome == "processed":
                    processed += 1
                elif outcome == "duplicate":
                    duplicates += 1
                    errors.append({"filename": filename, "error": detail})
                else:
                    failed += 1
                    errors.append({"filename": filename, "error": detail})
            except Exception as e:
                failed += 1
                errors.append({"filename": filename, "error": f"Processing error: {str(e)}"})

            # Intermediate commit
            batch.processed_count = processed
            batch.failed_count = failed
            batch.duplicate_count = duplicates
            batch.error_log = errors
            db.commit()

        batch.status = "completed" if (processed > 0 or duplicates > 0) else "failed"
        batch.processed_count = processed
        batch.failed_count = failed
        batch.duplicate_count = duplicates
        batch.error_log = errors
        db.commit()
    except Exception as e:
        print(f"Batch {batch_id} background task failed: {e}")
        try:
            batch.status = "failed"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/upload")
async def upload_resumes(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Multi-file resume upload endpoint.
    Enforces batch limits and per-file size limits.
    Processes asynchronously in background task.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > settings.INGEST_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds limit of {settings.INGEST_BATCH_SIZE} files per upload."
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    files_data = []

    for file in files:
        contents = await file.read()
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB."
            )
        files_data.append((file.filename, contents))

    # Create IngestionBatch row
    batch = IngestionBatch(
        created_by=current_user.id,
        total_files=len(files_data),
        processed_count=0,
        failed_count=0,
        duplicate_count=0,
        status="processing",
        error_log=[]
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # Queue async processing
    background_tasks.add_task(run_batch_ingestion_task, batch.id, files_data, current_user.id)

    return {
        "batch_id": batch.id,
        "status": "processing",
        "total_files": len(files_data),
        "message": "Resume batch upload accepted and queued for processing."
    }


@router.get("/batches")
def list_batches(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List ingestion batches."""
    query = db.query(IngestionBatch).order_by(IngestionBatch.created_at.desc())
    total = query.count()
    batches = query.offset(offset).limit(min(limit, 50)).all()
    return {
        "total": total,
        "batches": batches
    }


@router.get("/batches/{batch_id}")
def get_batch_status(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve detailed progress, counters, and error log for an ingestion batch."""
    batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Ingestion batch not found.")
    return batch
