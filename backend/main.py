import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import Base, engine
from backend.services.observability import ObservabilityMiddleware
from backend.services.opensearch import init_opensearch_index

# Import routers
from backend.routers import (
    auth,
    ingestion,
    job_descriptions,
    candidates,
    search,
    analytics,
    chat,
    export
)

# Initialize database tables
Base.metadata.create_all(bind=engine)

# Ensure upload directory exists
upload_path = Path(settings.STORAGE_DIR)
upload_path.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise AI-powered Hiring Platform",
    version="1.0.0"
)

# Observability middleware
app.add_middleware(ObservabilityMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static uploads
app.mount("/uploads", StaticFiles(directory=settings.STORAGE_DIR), name="uploads")


@app.on_event("startup")
async def startup_event():
    # Attempt to initialize OpenSearch index if cluster reachable
    try:
        init_opensearch_index()
    except Exception as e:
        print(f"Startup OpenSearch init note: {e}")


# Register routers
app.include_router(auth.router)
app.include_router(ingestion.router)
app.include_router(job_descriptions.router)
app.include_router(candidates.router)
app.include_router(search.router)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(export.router)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV
    }
