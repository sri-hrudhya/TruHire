import json
import logging
import time
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db, SessionLocal
from backend.models import User, Candidate, CandidateActivity, IngestionBatch, get_next_candidate_display_id
from backend.auth import get_current_user
from backend.rate_limit import limiter
from backend.services.common import ai_audit
from backend.services.common.cache import clear_cache, get_cache, set_cache, get_data_epoch
from backend.services.ingestion.storage import save_upload_file, compute_file_hash
from backend.services.ingestion.parsing import extract_text_from_file, parse_resume
from backend.services.ingestion.injection_screen import screen_resume
from backend.services.ingestion.pii import detect_pii, redact_pii
from backend.services.ingestion.chunking import profile_chunks, candidate_header
from backend.services.llm.ai_service import generate_embeddings_batch
from backend.services.retrieval.filters import index_payload_fields, set_candidate_filter_metadata
from backend.services.retrieval.opensearch import index_candidates_batch
from backend.services.retrieval.qdrant import upsert_candidates_batch, recreate_collection, collection_layout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


_profile_header = candidate_header


def _payload(candidate: Candidate) -> Dict:
    # location_keys / role_tokens are the filterable fields shared by Qdrant and OpenSearch.
    return {"candidate_id": candidate.id, "candidate_name": candidate.candidate_name, "current_company": candidate.current_company or "", "skills": candidate.extracted_skills or [], "years_experience": candidate.years_experience, "filename": candidate.original_filename,
            **index_payload_fields(candidate.location, candidate.job_titles)}


def index_candidate_documents(candidate: Candidate, raw_text: str) -> None:
    safe = redact_pii(raw_text, candidate_name=candidate.candidate_name)
    header = _profile_header(candidate)
    vectors = generate_embeddings_batch(profile_chunks(header, safe))
    payload = _payload(candidate)
    upsert_candidates_batch([(candidate.id, vectors, payload)])
    index_candidates_batch([(candidate.id, {**payload, "search_text": f"{header}\nResume: {safe}"})])
    candidate.opensearch_doc_id = candidate.id
    candidate.qdrant_point_id = candidate.id


class _Progress:
    """Writes live ingestion progress (overall stage + per-file status) to the batch row after
    every step, so the UI can poll it and show exactly what is happening to each resume."""

    def __init__(self, db: Session, batch: IngestionBatch, filenames: List[str]):
        self.db, self.batch = db, batch
        self.files = [{"filename": n, "status": "queued", "detail": ""} for n in filenames]

    def file(self, filename: str, status: str, detail: str = "") -> None:
        for f in self.files:
            if f["filename"] == filename and f["status"] not in ("indexed", "updated", "duplicate", "failed"):
                f["status"], f["detail"] = status, detail
                break
        self._flush()

    def stage(self, stage: str) -> None:
        self.batch.stage = stage
        self._flush()

    def _flush(self) -> None:
        self.batch.file_status = [dict(f) for f in self.files]  # reassign so SQLAlchemy sees the JSON change
        self.db.commit()

    def skip_remaining(self, detail: str) -> None:
        """Mark every file that has not reached a final state as skipped (used on cancel)."""
        final = ("indexed", "updated", "duplicate", "failed", "skipped")
        for f in self.files:
            if f["status"] not in final:
                f["status"], f["detail"] = "skipped", detail
        self._flush()


def _find_duplicate(db: Session, file_hash: str) -> Optional[Candidate]:
    # file_hash is not unique, so several rows can match; the newest one is "the" duplicate.
    return db.query(Candidate).filter(Candidate.file_hash == file_hash).order_by(Candidate.uploaded_at.desc()).first()


def _cancel_requested(db: Session, batch_id: str) -> bool:
    """Fresh read each call: the cancel endpoint commits from another session."""
    return bool(db.query(IngestionBatch.cancel_requested).filter(IngestionBatch.id == batch_id).scalar())


def process_batch(batch_id: str, files_data: List[tuple], user_id: str, duplicate_actions: Optional[Dict[str, str]] = None) -> None:
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
        prepared: List[Tuple[Candidate, str, str]] = []
        updated_ids: set = set()
        progress = _Progress(db, batch, [name for name, _ in files_data])
        progress.stage("reading")
        cancelled = False

        for filename, file_bytes in files_data:
            if _cancel_requested(db, batch_id):
                cancelled = True
                break
            try:
                progress.file(filename, "extracting", "Reading and extracting text")
                file_hash = compute_file_hash(file_bytes)
                existing = _find_duplicate(db, file_hash)
                # "update" re-ingests over the existing record; a second copy of a file already being
                # updated in this same batch is just a duplicate.
                updating = bool(existing) and (duplicate_actions or {}).get(filename) == "update" and existing.id not in updated_ids
                if existing and not updating:
                    duplicates += 1
                    progress.file(filename, "duplicate", f"Already uploaded as {existing.display_id or existing.candidate_name}")
                    errors.append({"filename": filename, "error": f"Skipped exact duplicate of candidate '{existing.candidate_name}' (ID: {existing.id})"})
                else:
                    raw_text = extract_text_from_file(filename, file_bytes)
                    screen = screen_resume(filename, file_bytes, raw_text) if raw_text.strip() else None
                    if not raw_text.strip():
                        failed += 1
                        progress.file(filename, "failed", "No readable text found")
                        errors.append({"filename": filename, "error": f"Failed to extract readable text from '{filename}'"})
                    elif screen.blocked:
                        # Rejected before anything is stored, parsed by the LLM or indexed.
                        failed += 1
                        progress.file(filename, "failed", "Rejected: hidden AI instructions detected")
                        errors.append({"filename": filename, "error": f"Rejected: resume contains hidden or embedded AI instructions ({screen.summary()})"})
                        ai_audit.record(provider="injection_screen", feature="resume_screen", status="blocked", prompt=raw_text,
                                        output=screen.hidden_text, details={"filename": filename, "reasons": screen.reasons, "batch_id": batch_id})
                    else:
                        if screen.borderline:
                            ai_audit.record(provider="injection_screen", feature="resume_screen", status="ok", prompt=raw_text,
                                            details={"filename": filename, "reasons": screen.reasons, "batch_id": batch_id})
                        file_url, _ = save_upload_file(filename, file_bytes)
                        progress.file(filename, "analyzing", "Extracting name, skills and experience with AI")
                        parsed = parse_resume(raw_text, filename)
                        pii_found = detect_pii(raw_text)
                        pii_detected = {category: len(matches) for category, matches in pii_found.items()}
                        fields = dict(resume_file_url=file_url, candidate_name=parsed["candidate_name"], email=parsed["email"],
                                      email_norm=(parsed["email"] or "").strip().casefold() or None,
                                      phone=parsed["phone"], phone_norm="".join(ch for ch in (parsed["phone"] or "") if ch.isdigit()) or None,
                                      current_company=parsed.get("current_company") or None,
                                      extracted_skills=parsed["extracted_skills"], years_experience=parsed["years_experience"], education=parsed["education"], resume_text=raw_text, pii_detected=pii_detected, uploaded_by=user_id, uploaded_at=datetime.utcnow(), ingestion_batch_id=batch_id, original_filename=filename)
                        if updating:
                            candidate = existing
                            for key, value in fields.items():
                                setattr(candidate, key, value)
                            updated_ids.add(candidate.id)
                        else:
                            candidate = Candidate(display_id=get_next_candidate_display_id(db), position_id=None, status="New", file_hash=file_hash, **fields)
                        set_candidate_filter_metadata(candidate, parsed.get("location"), parsed.get("job_titles"))
                        db.add(candidate); db.flush()
                        activity_actor = db.get(User, user_id)
                        db.add(CandidateActivity(candidate_id=candidate.id,
                            event_type="resume_updated" if updating else "resume_ingested",
                            actor_id=user_id, actor_name=activity_actor.name if activity_actor else None,
                            occurred_at=datetime.utcnow(), summary="Resume record updated." if updating else "Resume added to TruHire."))
                        safe = redact_pii(raw_text, candidate_name=candidate.candidate_name)
                        prepared.append((candidate, _profile_header(candidate), safe))
                        progress.file(filename, "parsed", f"{candidate.candidate_name} - waiting to be indexed")
            except Exception as exc:
                db.rollback()
                failed += 1
                progress.file(filename, "failed", str(exc)[:200])
                errors.append({"filename": filename, "error": str(exc)})
            # Deliberately outside the try/if-else above (not behind a `continue`,
            # which used to skip this entirely for duplicate/empty-text files and
            # left progress counters silently stuck at zero): every file, whichever
            # branch it took, must update visible batch progress.
            batch.processed_count = 0; batch.failed_count = failed; batch.duplicate_count = duplicates; batch.error_log = errors; db.commit()

        # A stop requested during parsing (or while the last files were being read) skips indexing:
        # parsed resumes stay in the DB unindexed, recoverable via POST /api/ingest/reindex?missing_only=true.
        if not cancelled:
            cancelled = _cancel_requested(db, batch_id)
        processed = 0
        if cancelled:
            progress.skip_remaining("Stopped by user")
            errors.append({"filename": "batch", "error": "Ingestion stopped by user before finishing."})
            batch.error_log = errors
        if prepared and not cancelled:
            try:
                progress.stage("embedding")
                chunk_lists = [profile_chunks(header, safe) for _, header, safe in prepared]
                for (cand, _, _), chunks in zip(prepared, chunk_lists):
                    progress.file(cand.original_filename, "embedding", f"Creating embeddings for {len(chunks)} chunk(s)")
                flat_vectors = generate_embeddings_batch([c for chunks in chunk_lists for c in chunks])
                qdrant_items = []
                opensearch_items = []
                offset = 0
                for (candidate, header, safe), chunks in zip(prepared, chunk_lists):
                    vectors = flat_vectors[offset:offset + len(chunks)]
                    offset += len(chunks)
                    payload = _payload(candidate)
                    qdrant_items.append((candidate.id, vectors, payload))
                    opensearch_items.append((candidate.id, {**payload, "search_text": f"{header}\nResume: {safe}"}))
                progress.stage("indexing")
                for cand, _, _ in prepared:
                    progress.file(cand.original_filename, "indexing", "Writing to vector + search indexes")
                upsert_candidates_batch(qdrant_items)
                index_candidates_batch(opensearch_items)
                # Only mark as indexed once both writes succeeded, so a failed batch stays
                # discoverable via POST /api/ingest/reindex?missing_only=true.
                for candidate, _, _ in prepared:
                    candidate.qdrant_point_id = candidate.id
                    candidate.opensearch_doc_id = candidate.id
                processed = len(prepared)
                for cand, _, _ in prepared:
                    was_update = cand.id in updated_ids
                    progress.file(cand.original_filename, "updated" if was_update else "indexed", f"{'Updated ' if was_update else ''}{cand.display_id} {cand.candidate_name}")
            except Exception as exc:
                failed += len(prepared)
                for cand, _, _ in prepared:
                    progress.file(cand.original_filename, "failed", f"Indexing failed: {str(exc)[:160]}")
                errors.append({"filename": "batch embedding/indexing", "error": str(exc)})
            batch.processed_count = processed; batch.failed_count = failed; batch.duplicate_count = duplicates; batch.error_log = errors; db.commit()

        batch.status = "cancelled" if cancelled else ("completed" if processed or duplicates else "failed")
        batch.stage = "done"
        logger.info("ingest batch=%s status=%s total=%s indexed=%s duplicates=%s failed=%s cancelled=%s", batch_id, batch.status, len(files_data), processed, duplicates, failed, cancelled)
        db.commit()
        clear_cache("candidates:list:")
        clear_cache("requirements:matches:")
        clear_cache("search:")
    except Exception as exc:
        db.rollback(); logger.warning(f"Batch {batch_id} failed: {exc}")
    finally:
        db.close()


@router.post("/upload")
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_resumes(request: Request, background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), duplicate_actions: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not files: raise HTTPException(status_code=400, detail="No files provided.")
    actions = _parse_duplicate_actions(duplicate_actions)
    if len(files) > settings.INGEST_BATCH_SIZE: raise HTTPException(status_code=400, detail=f"Batch size exceeds {settings.INGEST_BATCH_SIZE}.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024; files_data = []
    for file in files:
        contents = await file.read()
        if len(contents) > max_bytes: raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {settings.MAX_UPLOAD_MB} MB.")
        files_data.append((file.filename or "resume", contents))
    batch = IngestionBatch(created_by=current_user.id, total_files=len(files_data), status="processing", error_log=[], stage="queued",
                           file_status=[{"filename": n, "status": "queued", "detail": ""} for n, _ in files_data])
    db.add(batch); db.commit(); db.refresh(batch)

    enqueued = False
    if settings.USE_ARQ_QUEUE:
        try:
            from arq import create_pool
            pool = await create_pool(settings.get_arq_redis_settings())
            await pool.enqueue_job("process_batch_job", batch.id, files_data, current_user.id, actions)
            if hasattr(pool, "aclose"):
                await pool.aclose()
            else:
                await pool.close()
            enqueued = True
        except Exception as exc:
            logger.warning(f"Arq enqueue failed, falling back to BackgroundTasks: {exc}")

    if not enqueued:
        # Default local-dev mode (or fallback): zero extra infra required
        background_tasks.add_task(process_batch, batch.id, files_data, current_user.id, actions)

    return {"batch_id": batch.id, "status": "processing", "total_files": len(files_data), "message": "Resume batch upload accepted and queued."}


def _parse_duplicate_actions(raw: str) -> Dict[str, str]:
    """JSON {"filename": "update"|"skip"}; anything missing or invalid means skip (the old behavior)."""
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if v == "update"} if isinstance(data, dict) else {}


@router.post("/check-duplicates")
async def check_duplicates(files: List[UploadFile] = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Which of these files were already ingested (same bytes)? Hashes only; nothing is stored."""
    if len(files) > settings.INGEST_BATCH_SIZE: raise HTTPException(status_code=400, detail=f"Batch size exceeds {settings.INGEST_BATCH_SIZE}.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    duplicates = []
    for file in files:
        contents = await file.read()
        if len(contents) > max_bytes: raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {settings.MAX_UPLOAD_MB} MB.")
        existing = _find_duplicate(db, compute_file_hash(contents))
        if existing:
            uploader = db.query(User.name).filter(User.id == existing.uploaded_by).scalar()
            duplicates.append({"filename": file.filename or "resume", "candidate_id": existing.id, "display_id": existing.display_id,
                               "candidate_name": existing.candidate_name, "uploaded_at": _iso_utc(existing.uploaded_at), "uploaded_by": uploader})
    return {"duplicates": duplicates}


@router.get("/batches")
def list_batches(limit: int = 20, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(IngestionBatch).order_by(IngestionBatch.created_at.desc()); total = query.count()
    return {"total": total, "batches": query.offset(offset).limit(min(limit, 50)).all()}


@router.get("/batches/{batch_id}")
def get_batch_status(batch_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
    if not batch: raise HTTPException(status_code=404, detail="Ingestion batch not found.")
    return batch


@router.post("/batches/{batch_id}/cancel")
def cancel_batch(batch_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ask a running batch to stop. Cooperative: the worker notices between files and before
    the indexing stage, so a file already being parsed still finishes."""
    batch = db.query(IngestionBatch).filter(IngestionBatch.id == batch_id).first()
    if not batch: raise HTTPException(status_code=404, detail="Ingestion batch not found.")
    if batch.status != "processing": raise HTTPException(status_code=409, detail="Only a running upload can be stopped.")
    batch.cancel_requested = True
    db.commit()
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
                logger.warning(f"Reindex failed for candidate {cid}: {exc}")
    finally:
        session.close()
        clear_cache("requirements:matches:")
        clear_cache("search:")


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None  # stored naive-UTC; mark it so browsers convert correctly


@router.get("/history")
def ingestion_history(
    minutes: Optional[int] = None, status: str = "all", q: str = "", limit: int = 25, offset: int = 0,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Every document that went through ingestion, newest first.

    minutes: only documents from the last N minutes (omit for all time); status: all | indexed |
    duplicate | failed; q: matches file name, candidate name or display id. Indexed documents come
    from the candidates table; duplicate/failed attempts come from each batch's per-file outcome log.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    cutoff = datetime.utcnow() - timedelta(minutes=minutes) if minutes else None
    needle = q.strip().lower()
    if status not in ("all", "indexed", "duplicate", "failed"):
        raise HTTPException(status_code=400, detail="status must be all, indexed, duplicate or failed.")

    # The 10-second time bucket keeps relative windows ("last 10 min") moving with the clock.
    cache_key = f"ingest:history:{get_data_epoch()}:{int(time.time() // 10)}:{minutes}:{status}:{needle}:{limit}:{offset}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    rows: List[Dict] = []

    cq = db.query(Candidate, User.name).outerjoin(User, User.id == Candidate.uploaded_by)
    if cutoff:
        cq = cq.filter(Candidate.uploaded_at >= cutoff)
    for cand, uploader in cq.all():
        rows.append({
            "kind": "document", "status": "indexed" if (cand.qdrant_point_id and cand.opensearch_doc_id) else "pending_index",
            "uploaded_at": cand.uploaded_at, "filename": cand.original_filename, "detail": "",
            "candidate_id": cand.id, "display_id": cand.display_id, "candidate_name": cand.candidate_name,
            "years_experience": cand.years_experience, "skill_count": len(cand.extracted_skills or []),
            "batch_id": cand.ingestion_batch_id, "uploaded_by": uploader,
        })

    bq = db.query(IngestionBatch, User.name).outerjoin(User, User.id == IngestionBatch.created_by)
    if cutoff:
        bq = bq.filter(IngestionBatch.created_at >= cutoff)
    for batch, uploader in bq.all():
        outcomes = batch.file_status or [
            # Batches ingested before per-file tracking existed: derive outcomes from their error log.
            {"filename": e.get("filename"), "detail": e.get("error", ""),
             "status": "duplicate" if "duplicate" in e.get("error", "").lower() else "failed"}
            for e in (batch.error_log or []) if e.get("filename") not in (None, "batch embedding/indexing")
        ]
        for f in outcomes:
            if f.get("status") in ("duplicate", "failed"):
                rows.append({
                    "kind": "attempt", "status": f["status"], "uploaded_at": batch.created_at, "filename": f.get("filename"),
                    "detail": f.get("detail", ""), "candidate_id": None, "display_id": None, "candidate_name": None,
                    "years_experience": None, "skill_count": None, "batch_id": batch.id, "uploaded_by": uploader,
                })

    counts = {"indexed": 0, "duplicate": 0, "failed": 0}
    for r in rows:
        if r["status"] in counts:
            counts[r["status"]] += 1
    if status != "all":
        rows = [r for r in rows if r["status"] == status]
    if needle:
        rows = [r for r in rows if needle in " ".join(str(r.get(k) or "") for k in ("filename", "candidate_name", "display_id")).lower()]
    rows.sort(key=lambda r: r["uploaded_at"] or datetime.min, reverse=True)

    page = rows[offset:offset + limit]
    for r in page:
        r["uploaded_at"] = _iso_utc(r["uploaded_at"])
    result = {"total": len(rows), "limit": limit, "offset": offset, "counts": counts, "items": page}
    set_cache(cache_key, result, ttl_seconds=10)
    return result


def reparse_candidate(session: Session, candidate: Candidate) -> Dict:
    """Re-run field extraction on the stored resume text (improved parser) and re-index."""
    parsed = parse_resume(candidate.resume_text, candidate.original_filename)
    before = len(candidate.extracted_skills or [])
    candidate.candidate_name = parsed["candidate_name"] or candidate.candidate_name
    candidate.extracted_skills = parsed["extracted_skills"]
    candidate.years_experience = parsed["years_experience"]
    candidate.education = parsed["education"]
    candidate.email = parsed["email"] or candidate.email
    candidate.phone = parsed["phone"] or candidate.phone
    candidate.email_norm = (candidate.email or "").strip().casefold() or None
    candidate.phone_norm = "".join(ch for ch in (candidate.phone or "") if ch.isdigit()) or None
    candidate.current_company = parsed.get("current_company") or None
    # Unlike contact fields, an absent location/title replaces the old value: it reflects the resume as parsed now.
    set_candidate_filter_metadata(candidate, parsed.get("location"), parsed.get("job_titles"))
    session.flush()
    index_candidate_documents(candidate, candidate.resume_text)
    return {"id": candidate.id, "name": candidate.candidate_name, "skills_before": before, "skills_after": len(parsed["extracted_skills"])}


def _reparse_task(candidate_ids: List[str], user_id: str) -> None:
    ai_audit.set_user(user_id)
    session = SessionLocal()
    try:
        for cid in candidate_ids:
            candidate = session.get(Candidate, cid)
            if not candidate or not (candidate.resume_text or "").strip():
                continue
            try:
                info = reparse_candidate(session, candidate)
                session.commit()
                logger.info("reparsed %s %s skills %s -> %s", candidate.display_id, info["name"], info["skills_before"], info["skills_after"])
            except Exception as exc:
                session.rollback()
                logger.warning(f"Reparse failed for candidate {cid}: {exc}")
    finally:
        session.close()
        clear_cache("candidates:list:")
        clear_cache("requirements:matches:")
        clear_cache("search:")


@router.post("/reparse", status_code=202)
def reparse_candidates(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-extract name/skills/experience/education from every stored resume with the current parser
    and re-index. Use after a parser improvement; existing candidates keep their IDs."""
    ids = [row[0] for row in db.query(Candidate.id).all()]
    background_tasks.add_task(_reparse_task, ids, current_user.id)
    return {"status": "reparsing", "total_candidates": len(ids)}


@router.get("/index-status")
def index_status(current_user: User = Depends(get_current_user)):
    """Vector collection health: point count, on-disk vectors and quantization in effect."""
    return collection_layout()


@router.post("/reindex", status_code=202)
def reindex_candidates(background_tasks: BackgroundTasks, missing_only: bool = False, recreate: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-embed resumes into Qdrant and re-index them in OpenSearch, in the background.

    missing_only=true covers just the candidates that never reached the indexes (e.g. an
    interrupted batch); they are otherwise invisible to requirement matching. A full run is
    needed after changing the embedding model, so vectors from different models never mix.
    """
    if recreate and missing_only:
        raise HTTPException(status_code=400, detail="recreate=true re-indexes everyone; it cannot be combined with missing_only.")
    if recreate:
        # Drops the vector collection and recreates it with the on-disk + int8-quantized layout
        # (config: QDRANT_ON_DISK / QDRANT_QUANTIZATION). The re-index below repopulates it.
        recreate_collection(settings.EMBEDDING_DIM)
        db.query(Candidate).update({Candidate.qdrant_point_id: None})
        db.commit()
    query = db.query(Candidate.id)
    if missing_only:
        query = query.filter(Candidate.qdrant_point_id.is_(None))
    ids = [row[0] for row in query.all()]
    background_tasks.add_task(_reindex_task, ids, current_user.id)
    embedding_model = settings.LOCAL_EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == "local" else (settings.VLLM_EMBEDDING_MODEL or settings.EMBEDDING_MODEL)
    return {"status": "reindexing", "total_candidates": len(ids), "missing_only": missing_only, "recreated": recreate,
            "embedding_provider": settings.EMBEDDING_PROVIDER, "embedding_model": embedding_model}
