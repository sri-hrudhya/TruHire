from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db, SessionLocal
from backend.models import User, Candidate, IngestionBatch
from backend.auth import get_current_user
from backend.services.storage import save_upload_file, compute_file_hash
from backend.services.parsing import extract_text_from_file, heuristic_parse_resume
from backend.services.pii import redact_pii
from backend.services.ai_service import generate_embedding
from backend.services.opensearch import index_candidate, delete_candidate as delete_lexical
from backend.services.qdrant import upsert_candidate, delete_candidate as delete_vector

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def index_candidate_documents(candidate: Candidate, raw_text: str) -> None:
    safe = redact_pii(raw_text, candidate_name=candidate.candidate_name)
    profile_text = f"Name: {candidate.candidate_name}\nSkills: {', '.join(candidate.extracted_skills or [])}\nExperience: {candidate.years_experience}\nEducation: {candidate.education or ''}\nResume: {safe}"
    vector = generate_embedding(profile_text[:12000])
    payload = {"candidate_id": candidate.id, "candidate_name": candidate.candidate_name, "skills": candidate.extracted_skills or [], "years_experience": candidate.years_experience, "filename": candidate.original_filename}
    upsert_candidate(candidate.id, vector, payload)
    doc_id = index_candidate(candidate.id, {**payload, "search_text": profile_text})
    candidate.opensearch_doc_id = doc_id
    candidate.qdrant_point_id = candidate.id


@router.post("/reindex-embeddings")
def reindex_embeddings(db=Depends(get_db), user: User = Depends(get_current_user)):
    """Rebuild every candidate vector from the configured DGX/vLLM embedding model.

    This is intentionally explicit: embedding model/dimension changes must not silently
    mix vectors from different models in the same Qdrant collection.
    """
    candidates = db.query(Candidate).all()
    processed = 0
    for candidate in candidates:
        raw_text = candidate.resume_text or ""
        if not raw_text.strip():
            continue
        index_candidate_documents(candidate, raw_text)
        processed += 1
    db.commit()
    return {"reindexed": processed, "total_candidates": len(candidates), "embedding_provider": settings.EMBEDDING_PROVIDER, "embedding_model": settings.VLLM_EMBEDDING_MODEL or settings.EMBEDDING_MODEL}


def process_single_file(file_bytes: bytes, original_filename: str, batch_id: str, user_id: str, db: Session):
    file_hash = compute_file_hash(file_bytes)
    existing = db.query(Candidate).filter(Candidate.file_hash == file_hash).first()
    if existing: return "duplicate", f"Skipped exact duplicate of candidate '{existing.candidate_name}' (ID: {existing.id})"
    file_url, _ = save_upload_file(original_filename, file_bytes)
    raw_text = extract_text_from_file(original_filename, file_bytes)
    if not raw_text.strip(): return "failed", f"Failed to extract readable text from '{original_filename}'"
    parsed = heuristic_parse_resume(raw_text, original_filename)
    candidate = Candidate(position_id=None, resume_file_url=file_url, candidate_name=parsed["candidate_name"], email=parsed["email"], phone=parsed["phone"], extracted_skills=parsed["extracted_skills"], years_experience=parsed["years_experience"], education=parsed["education"], resume_text=raw_text, status="New", uploaded_by=user_id, uploaded_at=datetime.utcnow(), ingestion_batch_id=batch_id, file_hash=file_hash, original_filename=original_filename)
    db.add(candidate); db.flush()
    index_candidate_documents(candidate, raw_text)
    db.commit()
    return "processed", None


def run_batch_ingestion_task(batch_id: str, files_data: List[tuple], user_id: str):
    db = SessionLocal()
    try:
        batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
        if not batch: return
        processed = failed = duplicates = 0; errors = []
        for filename, file_bytes in files_data:
            try:
                outcome, detail = process_single_file(file_bytes, filename, batch_id, user_id, db)
                if outcome == "processed": processed += 1
                elif outcome == "duplicate": duplicates += 1; errors.append({"filename": filename, "error": detail})
                else: failed += 1; errors.append({"filename": filename, "error": detail})
            except Exception as exc:
                db.rollback(); failed += 1; errors.append({"filename": filename, "error": str(exc)})
            batch.processed_count = processed; batch.failed_count = failed; batch.duplicate_count = duplicates; batch.error_log = errors; db.commit()
        batch.status = "completed" if processed or duplicates else "failed"; db.commit()
    except Exception as exc:
        db.rollback(); print(f"Batch {batch_id} failed: {exc}")
    finally: db.close()


@router.post("/upload")
async def upload_resumes(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not files: raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > settings.INGEST_BATCH_SIZE: raise HTTPException(status_code=400, detail=f"Batch size exceeds {settings.INGEST_BATCH_SIZE}.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024; files_data = []
    for file in files:
        contents = await file.read()
        if len(contents) > max_bytes: raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {settings.MAX_UPLOAD_MB} MB.")
        files_data.append((file.filename or "resume", contents))
    batch = IngestionBatch(created_by=current_user.id, total_files=len(files_data), status="processing", error_log=[])
    db.add(batch); db.commit(); db.refresh(batch)
    background_tasks.add_task(run_batch_ingestion_task, batch.id, files_data, current_user.id)
    return {"batch_id": batch.id, "status": "processing", "total_files": len(files_data), "message": "Resume batch upload accepted and queued."}


@router.get("/batches")
def list_batches(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(IngestionBatch).order_by(IngestionBatch.created_at.desc()); total = query.count()
    return {"total": total, "batches": query.offset(offset).limit(min(limit, 50)).all()}


@router.get("/batches/{batch_id}")
def get_batch_status(batch_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
    if not batch: raise HTTPException(status_code=404, detail="Ingestion batch not found.")
    return batch


@router.post("/reindex")
def reindex_all_candidates(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidates = db.query(Candidate).all()
    def task(ids):
        session = SessionLocal()
        try:
            for cid in ids:
                c = session.query(Candidate).filter(Candidate.id == cid).first()
                if c and c.resume_text:
                    index_candidate_documents(c, c.resume_text); session.commit()
        finally: session.close()
    ids = [c.id for c in candidates]
    background_tasks.add_task(task, ids)
    return {"status": "reindexing", "total_candidates": len(ids), "message": "Existing resumes are being re-embedded into Qdrant and re-indexed in OpenSearch."}
