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
