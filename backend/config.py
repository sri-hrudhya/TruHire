import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App
    APP_NAME: str = "TruHire"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./truhire.db", description="Database connection URL")

    # Security & JWT
    SECRET_KEY: str = Field(
        default="truhire_dev_secret_key_change_me_in_production_9f83a2c",
        description="JWT secret signing key"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # AI Providers
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_FALLBACK_MODEL: str = "llama-3.3-70b-versatile"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    # Optional Gemini
    GEMINI_API_KEY: Optional[str] = None

    # Embeddings
    EMBEDDING_PROVIDER: str = "mock"  # 'mock', 'openrouter', or 'huggingface'
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 768

    # OpenSearch
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_USER: str = "admin"
    OPENSEARCH_PASSWORD: str = "admin"
    OPENSEARCH_INDEX: str = "truhire_candidates"

    # Bulk Ingestion
    INGEST_BATCH_SIZE: int = 50
    MAX_UPLOAD_MB: int = 15
    STORAGE_DIR: str = "./uploads"

    # Search & Ranking Constraints
    SEARCH_TOP_N: int = 20
    SEARCH_MAX_TOP_N: int = 100

    # Hybrid Scoring Weights
    SEMANTIC_WEIGHT: float = 0.45
    SKILL_WEIGHT: float = 0.35
    BASELINE_SCORE: float = 0.20
    EXPERIENCE_PENALTY: float = 0.10
    EDUCATION_PENALTY: float = 0.05

    # Analytics
    ANALYTICS_TOP_SKILLS: int = 20

    # Caching
    CACHE_TTL_QUERY: int = 300
    CACHE_TTL_CHAT: int = 600

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000"
    ]


settings = Settings()
