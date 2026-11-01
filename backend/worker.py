"""
Optional production-mode ingestion worker (arq). Only used when USE_ARQ_QUEUE=true
(Redis must be reachable); otherwise uploads run on FastAPI BackgroundTasks (see
routers/ingestion.py) with zero extra infrastructure.

Run as its own process, separate from the API server (docker compose runs it as the
`worker` service):

    arq backend.worker.WorkerSettings

This lets ingestion work continue after the API process restarts and keeps it from
competing with request handling on the same event loop.
"""
import asyncio

from backend.config import settings
from backend.routers.ingestion import process_batch


async def process_batch_job(ctx, batch_id: str, files_data: list, user_id: str) -> None:
    """arq task wrapper: same process_batch() the default BackgroundTasks path uses,
    so behavior is identical regardless of which queue backend is active.
    process_batch is blocking (OCR, embeddings), so it runs in a thread to keep the worker's
    event loop free for arq's health check and job timeouts."""
    await asyncio.to_thread(process_batch, batch_id, files_data, user_id)


class WorkerSettings:
    functions = [process_batch_job]
    redis_settings = settings.get_arq_redis_settings()
    max_jobs = 2                 # OCR/embedding is CPU heavy; scale with `--scale worker=N` instead of raising this
    job_timeout = 3600           # seconds; one batch of resumes
    max_tries = 2                # one retry if the worker dies mid-job (per-file dedupe makes a re-run safe)
    health_check_interval = 30   # keeps the key `arq --check` (compose healthcheck) reads fresh
