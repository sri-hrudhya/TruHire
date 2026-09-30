from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "TruHire"
    APP_ENV: str = "development"

    DATABASE_URL: str = Field(default="sqlite:///./truhire.db")

    SECRET_KEY: str = Field(default="truhire_dev_secret_key_change_me_in_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # OpenAI-compatible LLM/embedding server. Required, no default: an infra address
    # has no safe generic value (not a real address, not localhost either - a silent
    # localhost fallback would mask a missing/wrong .env just as much as a real one
    # baked into source would leak it). Set in .env; the app fails to start without it.
    VLLM_BASE_URL: str
    VLLM_API_KEY: Optional[str] = None
    VLLM_MODEL: Optional[str] = None
    VLLM_EMBEDDING_MODEL: Optional[str] = None
    VLLM_TIMEOUT: float = 120.0

    # Separate embedding server, since the DGX vLLM instance above only serves the
    # Qwen generation model and does not expose /v1/embeddings. Falls back to
    # VLLM_BASE_URL if unset (which will correctly fail with a 404 rather than
    # silently using the generation model).
    EMBEDDING_BASE_URL: Optional[str] = None
    VLLM_EMBEDDING_BASE_URL: Optional[str] = None
    VLLM_EMBEDDING_API_KEY: Optional[str] = None

    # Vector database. Required, no default - same reasoning as VLLM_BASE_URL above.
    QDRANT_URL: str
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "truhire_candidate_vectors"
    QDRANT_DISTANCE: str = "Cosine"

    # OpenSearch is retained for lexical/BM25 retrieval in the hybrid pipeline.
    # Required, no default - same reasoning as VLLM_BASE_URL above.
    OPENSEARCH_URL: str
    OPENSEARCH_USER: Optional[str] = None
    OPENSEARCH_PASSWORD: Optional[str] = None
    OPENSEARCH_INDEX: str = "truhire_candidates_v2"

    # "local" runs fastembed in-process (no API key, no external server); anything
    # else calls out to the configured vLLM-compatible embedding endpoint.
    EMBEDDING_PROVIDER: str = "local"
    LOCAL_EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_MODEL: Optional[str] = None
    EMBEDDING_DIM: int = 768

    # Laya: local non-autoregressive decision model (choice/score/noul), used as a fast
    # judgment layer instead of an LLM call for reranking, chat intent/decisions, and
    # guardrails. Falls back to the vLLM LLM path whenever Laya's own confidence is low
    # (its "escalate" action) or when it's disabled/unavailable.
    LAYA_ENABLED: bool = True
    LAYA_CONFIDENCE_THRESHOLD: float = 0.65
    LAYA_RERANK_WEIGHT: float = 0.20
    # Laya reranking only runs on a shortlist near the top of the deterministic
    # ranking, not the whole retrieval pool (which can be up to 500 candidates) - on
    # CPU-only hardware Laya measured ~0.4s/candidate even batched, so reranking the
    # full pool could add tens of seconds to a single search. This bounds that cost
    # while still reranking where it can actually change the final top_n.
    LAYA_RERANK_POOL_CAP: int = 50
    CACHE_TTL_DECISION: int = 3600

    INGEST_BATCH_SIZE: int = 50
    MAX_UPLOAD_MB: int = 15
    STORAGE_DIR: str = "./uploads"

    SEARCH_MAX_TOP_N: int = 100
    HYBRID_VECTOR_WEIGHT: float = 0.60
    HYBRID_LEXICAL_WEIGHT: float = 0.40
    HYBRID_RRF_K: int = 60
    SEARCH_CANDIDATE_MULTIPLIER: int = 5

    SEMANTIC_WEIGHT: float = 0.45
    SKILL_WEIGHT: float = 0.35
    BASELINE_SCORE: float = 0.20
    EXPERIENCE_PENALTY: float = 0.10
    EDUCATION_PENALTY: float = 0.05

    ANALYTICS_TOP_SKILLS: int = 20
    CACHE_TTL_QUERY: int = 30

    # Optional: enables the arq-backed production ingestion queue when set. Left unset,
    # ingestion uses FastAPI BackgroundTasks (today's behavior, zero extra infra).
    REDIS_URL: Optional[str] = None

    # Rate limiting (slowapi/limits syntax: "<count>/<second|minute|hour|day>").
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"
    RATE_LIMIT_DEFAULT: str = "60/minute"

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000"
    ]


settings = Settings()
