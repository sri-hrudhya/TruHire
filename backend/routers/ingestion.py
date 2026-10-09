from typing import Dict, List, Tuple
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db, SessionLocal
from backend.models import User, Candidate, IngestionBatch, get_next_candidate_display_id
from backend.auth import get_current_user
from backend.rate_limit import limiter
from backend.services.common import ai_audit
from backend.services.common.cache import clear_cache
from backend.services.ingestion.storage import save_upload_file, compute_file_hash
from backend.services.ingestion.parsing import extract_text_from_file, parse_resume
from backend.services.ingestion.injection_screen import screen_resume
from backend.services.ingestion.pii import detect_pii, redact_pii
from backend.services.llm.ai_service import generate_embedding, generate_embeddings_batch
from backend.services.retrieval.opensearch import index_candidate, index_candidates_batch
from backend.services.retrieval.qdrant import upsert_candidate, upsert_candidates_batch

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


def process_batch(batch_id: str, files_data: List[tuple], user_id: str) -> None:
    """
    The real ingestion path (used by both the default BackgroundTasks path and the
    optional arq worker - see backend/worker.py). Per-file work (dedupe, text
    extraction, LLM-based field parsing, PII detection) stays per-file since each
    resume needs its own structured extraction; the actual throughput bottleneck -
    embedding generation, Qdrant upsert, OpenSearch indexing - runs ONCE for the whole
    batch instead of once per resume.
    """
    # Runs outside the request (BackgroundTasks or the arq worker), so attribute AI calls explicitly.
    ai_audit.set_user(user_id)
    db = SessionLocal()
    try:
        batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
        if not batch:
            return

        duplicates = failed = 0
        errors: List[Dict[str, str]] = []
        prepared: List[Tuple[Candidate, str]] = []

        for filename, file_bytes in files_data:
            try:
                file_hash = compute_file_hash(file_bytes)
                existing = db.query(Candidate).filter(Candidate.file_hash == file_hash).first()
                if existing:
                    duplicates += 1
                    errors.append({"filename": filename, "error": f"Skipped exact duplicate of candidate '{existing.candidate_name}' (ID: {existing.id})"})
                else:
                    raw_text = extract_text_from_file(filename, file_bytes)
                    screen = screen_resume(filename, file_bytes, raw_text) if raw_text.strip() else None
                    if not raw_text.strip():
                        failed += 1
                        errors.append({"filename": filename, "error": f"Failed to extract readable text from '{filename}'"})
                    elif screen.blocked:
                        # Rejected before anything is stored, parsed by the LLM or indexed.
                        failed += 1
                        errors.append({"filename": filename, "error": f"Rejected: resume contains hidden or embedded AI instructions ({screen.summary()})"})
                        ai_audit.record(provider="injection_screen", feature="resume_screen", status="blocked", prompt=raw_text,
                                        output=screen.hidden_text, details={"filename": filename, "reasons": screen.reasons, "batch_id": batch_id})
                    else:
                        if screen.borderline:
                            ai_audit.record(provider="injection_screen", feature="resume_screen", status="ok", prompt=raw_text,
                                            details={"filename": filename, "reasons": screen.reasons, "batch_id": batch_id})
                        file_url, _ = save_upload_file(filename, file_bytes)
                        parsed = parse_resume(raw_text, filename)
                        pii_found = detect_pii(raw_text)
                        pii_detected = {category: len(matches) for category, matches in pii_found.items()}
                        display_id = get_next_candidate_display_id(db)
                        candidate = Candidate(display_id=display_id, position_id=None, resume_file_url=file_url, candidate_name=parsed["candidate_name"], email=parsed["email"], phone=parsed["phone"], extracted_skills=parsed["extracted_skills"], years_experience=parsed["years_experience"], education=parsed["education"], resume_text=raw_text, pii_detected=pii_detected, status="New", uploaded_by=user_id, uploaded_at=datetime.utcnow(), ingestion_batch_id=batch_id, file_hash=file_hash, original_filename=filename)
                        db.add(candidate); db.flush()
                        safe = redact_pii(raw_text, candidate_name=candidate.candidate_name)
                        profile_text = f"Name: {candidate.candidate_name}\nSkills: {', '.join(candidate.extracted_skills or [])}\nExperience: {candidate.years_experience}\nEducation: {candidate.education or ''}\nResume: {safe}"
                        prepared.append((candidate, profile_text[:12000]))
            except Exception as exc:
                db.rollback()
                failed += 1
                errors.append({"filename": filename, "error": str(exc)})
            # Deliberately outside the try/if-else above (not behind a `continue`,
            # which used to skip this entirely for duplicate/empty-text files and
            # left progress counters silently stuck at zero): every file, whichever
            # branch it took, must update visible batch progress.
            batch.processed_count = 0; batch.failed_count = failed; batch.duplicate_count = duplicates; batch.error_log = errors; db.commit()

        processed = 0
        if prepared:
            try:
                vectors = generate_embeddings_batch([text for _, text in prepared])
                qdrant_items = []
                opensearch_items = []
                for (candidate, profile_text), vector in zip(prepared, vectors):
                    payload = {"candidate_id": candidate.id, "candidate_name": candidate.candidate_name, "skills": candidate.extracted_skills or [], "years_experience": candidate.years_experience, "filename": candidate.original_filename}
                    qdrant_items.append((candidate.id, vector, payload))
                    opensearch_items.append((candidate.id, {**payload, "search_text": profile_text}))
                upsert_candidates_batch(qdrant_items)
                index_candidates_batch(opensearch_items)
                # Only mark as indexed once both writes succeeded, so a failed batch stays
                # discoverable via POST /api/ingest/reindex?missing_only=true.
                for candidate, _ in prepared:
                    candidate.qdrant_point_id = candidate.id
                    candidate.opensearch_doc_id = candidate.id
                processed = len(prepared)
            except Exception as exc:
                failed += len(prepared)
                errors.append({"filename": "batch embedding/indexing", "error": str(exc)})
            batch.processed_count = processed; batch.failed_count = failed; batch.duplicate_count = duplicates; batch.error_log = errors; db.commit()

        batch.status = "completed" if processed or duplicates else "failed"
        db.commit()
        clear_cache("candidates:list:")
        clear_cache("requirements:matches:")
        clear_cache("search:")
    except Exception as exc:
        db.rollback(); print(f"Batch {batch_id} failed: {exc}")
    finally:
        db.close()


@router.post("/upload")
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_resumes(request: Request, background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not files: raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > settings.INGEST_BATCH_SIZE: raise HTTPException(status_code=400, detail=f"Batch size exceeds {settings.INGEST_BATCH_SIZE}.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024; files_data = []
    for file in files:
        contents = await file.read()
        if len(contents) > max_bytes: raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {settings.MAX_UPLOAD_MB} MB.")
        files_data.append((file.filename or "resume", contents))
    batch = IngestionBatch(created_by=current_user.id, total_files=len(files_data), status="processing", error_log=[])
    db.add(batch); db.commit(); db.refresh(batch)

    enqueued = False
    if settings.USE_ARQ_QUEUE:
        try:
            from arq import create_pool
            pool = await create_pool(settings.get_arq_redis_settings())
            await pool.enqueue_job("process_batch_job", batch.id, files_data, current_user.id)
            if hasattr(pool, "aclose"):
                await pool.aclose()
            else:
                await pool.close()
            enqueued = True
        except Exception as exc:
            print(f"Arq enqueue failed, falling back to BackgroundTasks: {exc}")

    if not enqueued:
        # Default local-dev mode (or fallback): zero extra infra required
        background_tasks.add_task(process_batch, batch.id, files_data, current_user.id)

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


def _reindex_task(candidate_ids: List[str], user_id: str) -> None:
    ai_audit.set_user(user_id)
    session = SessionLocal()
    try:
        for cid in candidate_ids:
            candidate = session.get(Candidate, cid)
            if not candidate or not (candidate.resume_text or "").strip():
                continue
            try:
                index_candidate_documents(candidate, candidate.resume_text)
                session.commit()
            except Exception as exc:
                session.rollback()
                print(f"Reindex failed for candidate {cid}: {exc}")
    finally:
        session.close()
        clear_cache("requirements:matches:")
        clear_cache("search:")


@router.post("/reindex", status_code=202)
def reindex_candidates(background_tasks: BackgroundTasks, missing_only: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-embed resumes into Qdrant and re-index them in OpenSearch, in the background.

    missing_only=true covers just the candidates that never reached the indexes (e.g. an
    interrupted batch); they are otherwise invisible to requirement matching. A full run is
    needed after changing the embedding model, so vectors from different models never mix.
    """
    query = db.query(Candidate.id)
    if missing_only:
        query = query.filter(Candidate.qdrant_point_id.is_(None))
    ids = [row[0] for row in query.all()]
    background_tasks.add_task(_reindex_task, ids, current_user.id)
    embedding_model = settings.LOCAL_EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == "local" else (settings.VLLM_EMBEDDING_MODEL or settings.EMBEDDING_MODEL)
    return {"status": "reindexing", "total_candidates": len(ids), "missing_only": missing_only,
            "embedding_provider": settings.EMBEDDING_PROVIDER, "embedding_model": embedding_model}
