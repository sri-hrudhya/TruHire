import logging
import asyncio
import threading
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from backend.config import settings
from backend.logging_config import setup_logging
from backend.database import ensure_schema
from backend.rate_limit import limiter
from backend.services.common.observability import ObservabilityMiddleware
from backend.services.common.retention import schedule_retention_cleanup_task
from backend.services.retrieval.opensearch import init_opensearch_index
from backend.routers import auth, ingestion, job_descriptions, candidates, search, analytics, chat, export, retention, email, ai_audit

logger = logging.getLogger(__name__)

setup_logging()
logger = logging.getLogger("truhire")
ensure_schema()
Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.RESUME_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.JD_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.APP_NAME, description="Enterprise AI-powered Hiring Platform", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_origin_regex=(settings.CORS_ORIGIN_REGEX if settings.APP_ENV.lower() in ("development", "dev") else None), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
# Uploaded resumes/JDs are deliberately NOT served statically; they are streamed only via
# authenticated routes (GET /api/candidates/{id}/resume, GET /api/job-descriptions/{id}/file).

def _warm_models():
    """Load the local ML models once at startup (in a background thread) so the first search after a
    restart does not spend 30-60s loading them inside a user request."""
    import time
    started = time.perf_counter()
    steps = []
    if settings.EMBEDDING_PROVIDER == "local":
        from backend.services.llm import local_embeddings
        steps.append(("embeddings", local_embeddings._get_model))
    if settings.RERANKER_ENABLED:
        from backend.services.retrieval import reranker
        steps.append(("reranker", reranker._get_model))
    if settings.LAYA_ENABLED:
        from backend.services.llm import laya_service
        steps.append(("laya", laya_service._get_router))
    for name, load in steps:
        try:
            load()
        except Exception as exc:
            logger.warning("model warm-up skipped for %s: %s", name, exc)
    logger.info("model warm-up finished in %.1fs", time.perf_counter() - started)


@app.on_event("startup")
async def startup_event():
    logger.info("TruHire starting (env=%s, reranker=%s, qdrant_quantization=%s, qdrant_on_disk=%s)", settings.APP_ENV, settings.RERANKER_MODEL if settings.RERANKER_ENABLED else "off", settings.QDRANT_QUANTIZATION, settings.QDRANT_ON_DISK)
    try:
        init_opensearch_index()
    except Exception as exc:
        logger.warning(f"OpenSearch startup note: {exc}")
    threading.Thread(target=_warm_models, name="model-warmup", daemon=True).start()
    # Launch background data retention cleanup task
    asyncio.create_task(schedule_retention_cleanup_task())

for router in (
    auth.router,
    ingestion.router,
    job_descriptions.router,
    candidates.router,
    search.router,
    analytics.router,
    chat.router,
    export.router,
    retention.router,
    email.router,
    ai_audit.router,
):
    app.include_router(router)

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": settings.APP_NAME, "environment": settings.APP_ENV}
