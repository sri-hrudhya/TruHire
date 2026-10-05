from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, echo=False)
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor(); cursor.execute("PRAGMA foreign_keys=ON"); cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema():
    Base.metadata.create_all(bind=engine)
    if settings.DATABASE_URL.startswith("sqlite"):
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
            if "file_url" not in pos_cols:
                conn.execute(text("ALTER TABLE positions ADD COLUMN file_url VARCHAR"))
            if "original_filename" not in pos_cols:
                conn.execute(text("ALTER TABLE positions ADD COLUMN original_filename VARCHAR"))


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
