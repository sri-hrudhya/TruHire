import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import relationship
from backend.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    positions = relationship("Position", back_populates="creator")
    batches = relationship("IngestionBatch", back_populates="creator")


class Position(Base):
    """
    Position represents a Job Description (JD).
    JDs do not own candidates. They are versioned and used for matching and scoring.
    """
    __tablename__ = "positions"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False, index=True)
    jd_text = Column(Text, nullable=False)
    jd_summary = Column(Text, nullable=True)
    jd_version = Column(Integer, default=1, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", back_populates="positions")
    matches = relationship("CandidateMatch", back_populates="position", cascade="all, delete-orphan")


class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    id = Column(String, primary_key=True, default=generate_uuid)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_files = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    status = Column(String, default="processing")  # 'processing', 'completed', 'failed'
    error_log = Column(JSON, default=list)  # list of {"filename": str, "error": str}

    # Relationships
    creator = relationship("User", back_populates="batches")
    candidates = relationship("Candidate", back_populates="batch")


class Candidate(Base):
    """
    Candidate lives in a shared global pool.
    position_id is nullable (not owned by any single position).
    """
    __tablename__ = "candidates"

    id = Column(String, primary_key=True, default=generate_uuid)
    position_id = Column(String, ForeignKey("positions.id"), nullable=True)
    resume_file_url = Column(String, nullable=True)
    candidate_name = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    extracted_skills = Column(JSON, default=list)  # ["Python", "Docker", "FastAPI"]
    years_experience = Column(Float, default=0.0)
    education = Column(Text, nullable=True)
    status = Column(String, default="New", index=True)  # New -> Shortlisted -> Interviewed -> Rejected
    status_updated_by = Column(String, nullable=True)
    status_updated_at = Column(DateTime, nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    ingestion_batch_id = Column(String, ForeignKey("ingestion_batches.id"), nullable=True)
    file_hash = Column(String, nullable=False, index=True)  # SHA-256 for duplicate detection
    original_filename = Column(String, nullable=False)
    opensearch_doc_id = Column(String, nullable=True)

    # Relationships
    batch = relationship("IngestionBatch", back_populates="candidates")
    matches = relationship("CandidateMatch", back_populates="candidate", cascade="all, delete-orphan")


class CandidateMatch(Base):
    """
    One row per (candidate_id, position_id) pair.
    Stores match score, detailed breakdown, citations, and JD version at match time.
    """
    __tablename__ = "candidate_matches"

    id = Column(String, primary_key=True, default=generate_uuid)
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=False)
    position_id = Column(String, ForeignKey("positions.id"), nullable=False)
    match_score = Column(Float, nullable=False, index=True)  # 0 to 100
    score_breakdown = Column(JSON, default=dict)  # {"semantic": ..., "skill": ..., "experience": ..., "education": ...}
    llm_summary = Column(Text, nullable=True)
    cited_quote = Column(Text, nullable=True)
    cited_section = Column(Text, nullable=True)
    jd_version = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="matches")
    position = relationship("Position", back_populates="matches")

    __table_args__ = (
        UniqueConstraint("candidate_id", "position_id", name="uq_candidate_position"),
        Index("idx_candidate_match_score", "position_id", "match_score"),
    )
