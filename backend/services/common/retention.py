import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Candidate, CandidateMatch, Conversation, IngestionBatch, Position, SearchState
from backend.services.ingestion.storage import delete_file_by_url_or_path
from backend.services.retrieval.opensearch import delete_candidates_batch as delete_opensearch_batch
from backend.services.retrieval.qdrant import delete_candidates_batch as delete_qdrant_batch


def _clean_orphaned_directory_files(directory_path: str, cutoff_timestamp: float) -> int:
    """Removes files in directory that are older than cutoff_timestamp."""
    deleted_count = 0
    dir_path = Path(directory_path)
    if not dir_path.exists() or not dir_path.is_dir():
        return 0

    try:
        for file_path in dir_path.iterdir():
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    if mtime < cutoff_timestamp:
                        file_path.unlink()
                        deleted_count += 1
                except Exception as exc:
                    print(f"Error checking/deleting file {file_path}: {exc}")
    except Exception as exc:
        print(f"Error scanning directory {directory_path}: {exc}")

    return deleted_count


def cleanup_expired_resumes(db: Session, retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Purges candidate resumes, vector embeddings, and search index documents
    older than the configured retention period.
    """
    days = retention_days if retention_days is not None else settings.effective_resume_retention_days
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    expired_candidates = db.query(Candidate).filter(Candidate.uploaded_at < cutoff).all()
    candidate_ids = [c.id for c in expired_candidates]
    deleted_files = 0

    # 1. Delete physical files associated with expired candidates
    for c in expired_candidates:
        if c.resume_file_url:
            if delete_file_by_url_or_path(c.resume_file_url):
                deleted_files += 1

    # 2. Batch remove points from Qdrant vector DB & OpenSearch
    if candidate_ids:
        try:
            delete_qdrant_batch(candidate_ids)
        except Exception as exc:
            print(f"Retention: error deleting Qdrant vectors: {exc}")

        try:
            delete_opensearch_batch(candidate_ids)
        except Exception as exc:
            print(f"Retention: error deleting OpenSearch docs: {exc}")

        # 3. Clean up related database rows
        # Cascade deletes CandidateMatch
        db.query(CandidateMatch).filter(CandidateMatch.candidate_id.in_(candidate_ids)).delete(synchronize_session=False)

        # Remove conversations referencing candidate
        db.query(Conversation).filter(Conversation.candidate_id.in_(candidate_ids)).delete(synchronize_session=False)

        # Delete candidates
        db.query(Candidate).filter(Candidate.id.in_(candidate_ids)).delete(synchronize_session=False)

    # 4. Clean up any orphaned physical files in the resumes storage folder older than cutoff
    orphaned_files = _clean_orphaned_directory_files(settings.RESUME_STORAGE_DIR, cutoff_ts)
    deleted_files += orphaned_files

    # 5. Clean up completed/failed ingestion batches older than cutoff with no remaining candidates
    try:
        old_batches = db.query(IngestionBatch).filter(IngestionBatch.created_at < cutoff).all()
        for batch in old_batches:
            remaining = db.query(Candidate).filter(Candidate.ingestion_batch_id == batch.id).count()
            if remaining == 0:
                db.delete(batch)
    except Exception as exc:
        print(f"Retention: error cleaning old batches: {exc}")

    db.commit()

    return {
        "retention_days": days,
        "cutoff_date": cutoff.isoformat(),
        "candidates_deleted": len(candidate_ids),
        "files_deleted": deleted_files,
        "embeddings_deleted": len(candidate_ids),
    }


def cleanup_expired_jds(db: Session, retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Purges job descriptions (Positions) and associated uploaded files
    older than the configured retention period.
    """
    days = retention_days if retention_days is not None else settings.effective_jd_retention_days
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    expired_positions = db.query(Position).filter(Position.created_at < cutoff).all()
    position_ids = [p.id for p in expired_positions]
    deleted_files = 0

    for p in expired_positions:
        if p.file_url:
            if delete_file_by_url_or_path(p.file_url):
                deleted_files += 1

    if position_ids:
        # Delete related candidate matches
        db.query(CandidateMatch).filter(CandidateMatch.position_id.in_(position_ids)).delete(synchronize_session=False)

        # Clear position_id from search states
        db.query(SearchState).filter(SearchState.position_id.in_(position_ids)).update(
            {"position_id": None}, synchronize_session=False
        )

        # Clear position_id from conversations
        db.query(Conversation).filter(Conversation.position_id.in_(position_ids)).update(
            {"position_id": None}, synchronize_session=False
        )

        # Delete positions
        db.query(Position).filter(Position.id.in_(position_ids)).delete(synchronize_session=False)

    # Clean up any orphaned files in the JD storage folder older than cutoff
    orphaned_files = _clean_orphaned_directory_files(settings.JD_STORAGE_DIR, cutoff_ts)
    deleted_files += orphaned_files

    db.commit()

    return {
        "retention_days": days,
        "cutoff_date": cutoff.isoformat(),
        "jds_deleted": len(position_ids),
        "files_deleted": deleted_files,
    }


def run_retention_cleanup(
    db: Optional[Session] = None,
    resume_retention_days: Optional[int] = None,
    jd_retention_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes full data retention purge for both candidate resumes & chunks/embeddings
    and job descriptions.
    """
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    try:
        resume_stats = cleanup_expired_resumes(db, retention_days=resume_retention_days)
        jd_stats = cleanup_expired_jds(db, retention_days=jd_retention_days)

        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "resumes": resume_stats,
            "job_descriptions": jd_stats,
            "total_files_deleted": resume_stats["files_deleted"] + jd_stats["files_deleted"],
            "total_candidates_deleted": resume_stats["candidates_deleted"],
            "total_jds_deleted": jd_stats["jds_deleted"],
        }
        print(f"Data retention cleanup completed: {summary}")
        return summary
    finally:
        if own_session:
            db.close()


def get_retention_status(db: Session) -> Dict[str, Any]:
    """
    Returns current data retention configuration, cutoffs, and expired record counts.
    """
    resume_days = settings.effective_resume_retention_days
    jd_days = settings.effective_jd_retention_days

    resume_cutoff = datetime.utcnow() - timedelta(days=resume_days)
    jd_cutoff = datetime.utcnow() - timedelta(days=jd_days)

    expired_candidates = db.query(Candidate).filter(Candidate.uploaded_at < resume_cutoff).count()
    expired_positions = db.query(Position).filter(Position.created_at < jd_cutoff).count()

    total_candidates = db.query(Candidate).count()
    total_positions = db.query(Position).count()

    return {
        "data_retention_days": settings.DATA_RETENTION_DAYS,
        "resume_retention_days": resume_days,
        "jd_retention_days": jd_days,
        "cleanup_interval_hours": settings.RETENTION_CLEANUP_INTERVAL_HOURS,
        "resume_cutoff_date": resume_cutoff.isoformat(),
        "jd_cutoff_date": jd_cutoff.isoformat(),
        "expired_candidates_count": expired_candidates,
        "expired_positions_count": expired_positions,
        "total_candidates": total_candidates,
        "total_positions": total_positions,
    }


async def schedule_retention_cleanup_task() -> None:
    """
    Background worker loop that runs periodically to enforce data retention policies.
    """
    interval_hours = settings.RETENTION_CLEANUP_INTERVAL_HOURS
    if interval_hours <= 0:
        print("Data retention auto-cleanup worker is disabled (interval <= 0).")
        return

    # Initial short delay on startup before first check
    await asyncio.sleep(5)

    while True:
        try:
            print(f"Starting scheduled data retention cleanup (retention: {settings.DATA_RETENTION_DAYS} days)...")
            run_retention_cleanup()
        except Exception as exc:
            print(f"Error during scheduled retention cleanup: {exc}")

        # Sleep until next cycle
        await asyncio.sleep(interval_hours * 3600)
