from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# PostgreSQL: pooled connections, validated before use so a restarted database server
# does not surface as errors on the next requests.
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema():
    Base.metadata.create_all(bind=engine)
    # Additive, idempotent column upgrades for databases created before a column existed.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE ingestion_batches ADD COLUMN IF NOT EXISTS stage VARCHAR"))
        conn.execute(text("ALTER TABLE ingestion_batches ADD COLUMN IF NOT EXISTS file_status JSON"))
        # Location / role filters (candidate metadata, JD-derived defaults, saved search state).
        for stmt in (
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location VARCHAR",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location_norm VARCHAR",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_titles JSON",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS title_norms VARCHAR",
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS search_filters JSON",
            "ALTER TABLE search_states ADD COLUMN IF NOT EXISTS location VARCHAR",
            "ALTER TABLE search_states ADD COLUMN IF NOT EXISTS role VARCHAR",
        ):
            conn.execute(text(stmt))
    from backend.models import Candidate, Position, CANDIDATE_ID_PREFIX, POSITION_ID_PREFIX, seed_id_sequence
    db = SessionLocal()
    try:
        seed_id_sequence(db, Position, POSITION_ID_PREFIX)
        seed_id_sequence(db, Candidate, CANDIDATE_ID_PREFIX)
        db.commit()
    finally:
        db.close()



def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
