"""
Optional production-mode ingestion worker (arq). Only used when REDIS_URL is set in
.env - local dev keeps using FastAPI BackgroundTasks (see routers/ingestion.py) with
zero extra infrastructure.

Run as its own process, separate from the API server:

    arq backend.worker.WorkerSettings

This lets ingestion work continue after the API process restarts and keeps it from
competing with request handling on the same event loop.
"""
from arq.connections import RedisSettings

from backend.config import settings
from backend.routers.ingestion import process_batch


async def process_batch_job(ctx, batch_id: str, files_data: list, user_id: str) -> None:
    """arq task wrapper: same process_batch() the default BackgroundTasks path uses,
    so behavior is identical regardless of which queue backend is active."""
    process_batch(batch_id, files_data, user_id)


class WorkerSettings:
    functions = [process_batch_job]
    redis_settings = settings.get_arq_redis_settings()
