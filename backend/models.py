import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from backend.database import Base


def generate_uuid(): return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    positions = relationship("Position", back_populates="creator")
    batches = relationship("IngestionBatch", back_populates="creator")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"
    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False, index=True)
    jd_text = Column(Text, nullable=False)
    jd_summary = Column(Text, nullable=True)
    jd_version = Column(Integer, default=1, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    status = Column(String, default="processing")
    error_log = Column(JSON, default=list)
    creator = relationship("User", back_populates="batches")
    candidates = relationship("Candidate", back_populates="batch")


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(String, primary_key=True, default=generate_uuid)
    position_id = Column(String, ForeignKey("positions.id"), nullable=True)
    resume_file_url = Column(String, nullable=True)
    candidate_name = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    extracted_skills = Column(JSON, default=list)
    years_experience = Column(Float, default=0.0)
    education = Column(Text, nullable=True)
    resume_text = Column(Text, nullable=True)
    status = Column(String, default="New", index=True)
    status_updated_by = Column(String, nullable=True)
    status_updated_at = Column(DateTime, nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    ingestion_batch_id = Column(String, ForeignKey("ingestion_batches.id"), nullable=True)
    file_hash = Column(String, nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    opensearch_doc_id = Column(String, nullable=True)
    qdrant_point_id = Column(String, nullable=True)
    batch = relationship("IngestionBatch", back_populates="candidates")
    matches = relationship("CandidateMatch", back_populates="candidate", cascade="all, delete-orphan")


class CandidateMatch(Base):
    __tablename__ = "candidate_matches"
    id = Column(String, primary_key=True, default=generate_uuid)
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=False)
    position_id = Column(String, ForeignKey("positions.id"), nullable=False)
    match_score = Column(Float, nullable=False, index=True)
    score_breakdown = Column(JSON, default=dict)
    llm_summary = Column(Text, nullable=True)
    cited_quote = Column(Text, nullable=True)
    cited_section = Column(Text, nullable=True)
    jd_version = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    candidate = relationship("Candidate", back_populates="matches")
    position = relationship("Position", back_populates="matches")
    __table_args__ = (UniqueConstraint("candidate_id", "position_id", name="uq_candidate_position"), Index("idx_candidate_match_score", "position_id", "match_score"))


class SearchState(Base):
    __tablename__ = "search_states"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    query = Column(Text, default="", nullable=False)
    filter_skills = Column(JSON, default=list)
    min_experience = Column(Float, nullable=True)
    position_id = Column(String, ForeignKey("positions.id", ondelete="SET NULL"), nullable=True, index=True)
    top_n = Column(Integer, default=20, nullable=False)
    results = Column(JSON, default=list)
    total_matches = Column(Integer, default=0, nullable=False)
    retrieval = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=True, index=True)
    position_id = Column(String, ForeignKey("positions.id"), nullable=True, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    conversation = relationship("Conversation", back_populates="messages")
