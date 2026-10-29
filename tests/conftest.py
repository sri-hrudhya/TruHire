import os

# Unit/integration tests must never download or run the real cross-encoder model.
os.environ.setdefault("RERANKER_ENABLED", "false")


def _use_isolated_test_database() -> None:
    """Point the suite at a separate `<db>_test` PostgreSQL database (created on demand),
    so tests never read or write real TruHire data."""
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    url = os.environ.get("DATABASE_URL") or dotenv_values(".env").get("DATABASE_URL")
    if not url:
        return
    parsed = make_url(url)
    test_db = parsed.database if parsed.database.endswith("_test") else f"{parsed.database}_test"
    import psycopg

    admin = parsed.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,)).fetchone():
            conn.execute(f'CREATE DATABASE "{test_db}"')
    os.environ["DATABASE_URL"] = parsed.set(database=test_db).render_as_string(hide_password=False)


_use_isolated_test_database()


import pytest


@pytest.fixture(scope="session", autouse=True)
def _baseline_data():
    """The isolated test database starts empty; a few tests browse 'existing' records, so
    guarantee one user, candidate and requirement exist (created once, never removed)."""
    from datetime import datetime
    from backend.auth import get_password_hash
    from backend.database import SessionLocal, ensure_schema
    from backend.models import Candidate, Position, User, get_next_candidate_display_id, get_next_position_display_id

    ensure_schema()
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(email="seed@truhire.test", name="Seed User", hashed_password=get_password_hash("seed-pass-123"))
            db.add(user)
            db.flush()
        if not db.query(Candidate).first():
            db.add(Candidate(display_id=get_next_candidate_display_id(db), candidate_name="Seed Candidate", email="seed.candidate@example.com",
                             extracted_skills=["Python"], years_experience=5, education="BSc University", resume_text="Python engineer",
                             status="New", uploaded_by=user.id, uploaded_at=datetime.utcnow(), file_hash="seed-baseline", original_filename="seed.pdf"))
        if not db.query(Position).first():
            db.add(Position(display_id=get_next_position_display_id(db), title="Seed Requirement", jd_text="Python engineer with FastAPI.", created_by=user.id))
        db.commit()
    finally:
        db.close()
    yield
