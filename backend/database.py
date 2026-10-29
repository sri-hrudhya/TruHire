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
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS display_id VARCHAR",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS display_id VARCHAR",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_positions_display_id ON positions (display_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_candidates_display_id ON candidates (display_id)",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location VARCHAR",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location_norm VARCHAR",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS job_titles JSON",
            "ALTER TABLE candidates ADD COLUMN IF NOT EXISTS title_norms VARCHAR",
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS search_filters JSON",
            "ALTER TABLE search_states ADD COLUMN IF NOT EXISTS location VARCHAR",
            "ALTER TABLE search_states ADD COLUMN IF NOT EXISTS role VARCHAR",
            # Demands: optional grouping of positions (the demands table itself is made by create_all above).
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS demand_id VARCHAR REFERENCES demands(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_positions_demand_id ON positions (demand_id)",
            "ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS metadata JSON NOT NULL DEFAULT '{}'::json",
            # System-seeded demands have no creating user.
            "ALTER TABLE demands ALTER COLUMN created_by DROP NOT NULL",
        ):
            conn.execute(text(stmt))
        _seed_default_demands(conn)
    from backend import models  # noqa: F401  (registers every table on Base.metadata)
    _add_missing_columns()
    with engine.begin() as conn:
        conn.execute(text("UPDATE positions SET status = 'Open' WHERE status IS NULL"))
        conn.execute(text("UPDATE positions SET status = 'Mapped' WHERE status = 'Map'"))
        conn.execute(text("UPDATE positions SET status = 'Cancelled' WHERE status = 'Closed'"))  # Closed no longer exists
        # Demand IDs were renamed from TRU-JD-nnnn to DM-nnnn; carry existing rows, history snapshots and the counter over.
        conn.execute(text("UPDATE positions SET display_id = 'DM-' || substr(display_id, 8) WHERE display_id LIKE 'TRU-JD-%'"))
        for table, col in (("requirement_history", "item_display_id"), ("email_records", "position_display_id")):
            conn.execute(text(f"UPDATE {table} SET {col} = 'DM-' || substr({col}, 8) WHERE {col} LIKE 'TRU-JD-%'"))
        conn.execute(text("UPDATE id_sequences SET name = 'DM-' WHERE name = 'TRU-JD-' AND NOT EXISTS (SELECT 1 FROM id_sequences WHERE name = 'DM-')"))
    from backend.models import Candidate, Position, CANDIDATE_ID_PREFIX, POSITION_ID_PREFIX, seed_id_sequence
    db = SessionLocal()
    try:
        seed_id_sequence(db, Position, POSITION_ID_PREFIX)
        seed_id_sequence(db, Candidate, CANDIDATE_ID_PREFIX)
        db.commit()
    finally:
        db.close()



def _seed_default_demands(conn):
    """Make the five fixed Demand categories the only Demands. Idempotent and safe to repeat:

    1. Each canonical record (id ``default-demand-<name>``) is upserted.
    2. Legacy demands whose name matches a canonical one (any case/whitespace) hand their JDs to it;
       every other legacy demand hands its JDs to "Others". Foreign keys are repointed before the
       legacy row is removed, so no JD, version or match record is touched.
    3. JDs without a category are classified from their content (same service as create/upload).
    """
    from backend.models import DEFAULT_DEMAND_NAMES, OTHERS_DEMAND_NAME, canonical_demand_id
    # Serialise concurrent workers starting up at the same time.
    conn.execute(text("SELECT pg_advisory_xact_lock(748201)"))
    for name in DEFAULT_DEMAND_NAMES:
        conn.execute(text(
            "INSERT INTO demands (id, name, description, created_by, created_at, updated_at) "
            "VALUES (CAST(:id AS VARCHAR), CAST(:name AS VARCHAR), NULL, NULL, (now() AT TIME ZONE 'utc'), (now() AT TIME ZONE 'utc')) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"
        ), {"id": canonical_demand_id(name), "name": name})
    canonical_ids = [canonical_demand_id(n) for n in DEFAULT_DEMAND_NAMES]
    legacy = conn.execute(text("SELECT id, name FROM demands WHERE id <> ALL(:ids)"), {"ids": canonical_ids}).fetchall()
    by_lower = {n.lower(): n for n in DEFAULT_DEMAND_NAMES}
    for legacy_id, legacy_name in legacy:
        target = canonical_demand_id(by_lower.get((legacy_name or "").strip().lower(), OTHERS_DEMAND_NAME))
        conn.execute(text("UPDATE positions SET demand_id = :t WHERE demand_id = :l"), {"t": target, "l": legacy_id})
        conn.execute(text("DELETE FROM demands WHERE id = :l"), {"l": legacy_id})
    from backend.services.classification import classify_jd
    for pos_id, title, jd_text in conn.execute(text("SELECT id, title, jd_text FROM positions WHERE demand_id IS NULL")).fetchall():
        conn.execute(text("UPDATE positions SET demand_id = :d WHERE id = :p"),
                     {"d": canonical_demand_id(classify_jd(title, jd_text)), "p": pos_id})


def _add_missing_columns():
    """Add model columns absent from tables created by an older version (create_all never alters).

    Columns are added nullable and without defaults so this is safe on tables that already hold rows.
    """
    from sqlalchemy import inspect
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                coltype = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{col.name}" {coltype}'))


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
