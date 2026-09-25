from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.database import ensure_schema
from backend.services.observability import ObservabilityMiddleware
from backend.services.opensearch import init_opensearch_index
from backend.routers import auth, ingestion, job_descriptions, candidates, search, analytics, chat, export

ensure_schema()
Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
app = FastAPI(title=settings.APP_NAME, description="Enterprise AI-powered Hiring Platform", version="2.0.0")
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=settings.STORAGE_DIR), name="uploads")

@app.on_event("startup")
async def startup_event():
    try: init_opensearch_index()
    except Exception as exc: print(f"OpenSearch startup note: {exc}")

for router in (auth.router, ingestion.router, job_descriptions.router, candidates.router, search.router, analytics.router, chat.router, export.router):
    app.include_router(router)

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": settings.APP_NAME, "environment": settings.APP_ENV}
