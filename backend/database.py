from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
else:
    # PostgreSQL (postgresql+psycopg://...): pooled connections, validated before use so a
    # restarted database server doesn't surface as errors on the next requests.
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
    )
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor(); cursor.execute("PRAGMA foreign_keys=ON"); cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema():
    Base.metadata.create_all(bind=engine)
    # Legacy in-place column upgrades for older SQLite dev databases; PostgreSQL databases
    # are created complete by create_all (or populated by scripts/migrate_sqlite_to_postgres.py).
    if IS_SQLITE:
        import re
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        cols = {c["name"] for c in inspector.get_columns("candidates")} if "candidates" in table_names else set()
        pos_cols = {c["name"] for c in inspector.get_columns("positions")} if "positions" in table_names else set()
        with engine.begin() as conn:
            if "resume_text" not in cols:
                conn.execute(text("ALTER TABLE candidates ADD COLUMN resume_text TEXT"))
            if "qdrant_point_id" not in cols:
                conn.execute(text("ALTER TABLE candidates ADD COLUMN qdrant_point_id VARCHAR"))
            if "pii_detected" not in cols:
                conn.execute(text("ALTER TABLE candidates ADD COLUMN pii_detected TEXT"))
            if "display_id" not in cols:
                conn.execute(text("ALTER TABLE candidates ADD COLUMN display_id VARCHAR"))
            if "file_url" not in pos_cols:
                conn.execute(text("ALTER TABLE positions ADD COLUMN file_url VARCHAR"))
            if "original_filename" not in pos_cols:
                conn.execute(text("ALTER TABLE positions ADD COLUMN original_filename VARCHAR"))
            if "display_id" not in pos_cols:
                conn.execute(text("ALTER TABLE positions ADD COLUMN display_id VARCHAR"))

            # Backfill existing positions lacking display_id
            pos_unassigned = conn.execute(text("SELECT id FROM positions WHERE display_id IS NULL ORDER BY created_at ASC, id ASC")).fetchall()
            if pos_unassigned:
                max_pos_rows = conn.execute(text("SELECT display_id FROM positions WHERE display_id IS NOT NULL")).fetchall()
                max_pos = 0
                for (d_id,) in max_pos_rows:
                    if d_id and d_id.startswith("TRU-JD-"):
                        m = re.search(r"TRU-JD-(\d+)", d_id)
                        if m:
                            max_pos = max(max_pos, int(m.group(1)))
                for row in pos_unassigned:
                    max_pos += 1
                    conn.execute(text("UPDATE positions SET display_id = :did WHERE id = :id"), {"did": f"TRU-JD-{max_pos:04d}", "id": row[0]})

            # Backfill existing candidates lacking display_id
            cand_unassigned = conn.execute(text("SELECT id FROM candidates WHERE display_id IS NULL ORDER BY uploaded_at ASC, id ASC")).fetchall()
            if cand_unassigned:
                max_cand_rows = conn.execute(text("SELECT display_id FROM candidates WHERE display_id IS NOT NULL")).fetchall()
                max_cand = 0
                for (d_id,) in max_cand_rows:
                    if d_id and d_id.startswith("TRU-CN-"):
                        m = re.search(r"TRU-CN-(\d+)", d_id)
                        if m:
                            max_cand = max(max_cand, int(m.group(1)))
                for row in cand_unassigned:
                    max_cand += 1
                    conn.execute(text("UPDATE candidates SET display_id = :did WHERE id = :id"), {"did": f"TRU-CN-{max_cand:04d}", "id": row[0]})

            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_display_id ON candidates(display_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_display_id ON positions(display_id)"))

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
