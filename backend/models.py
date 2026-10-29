import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Date, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from backend.database import Base


def generate_uuid(): return str(uuid.uuid4())


ROLE_ADMIN = "admin"
ROLE_RECRUITER = "recruiter"
ROLES = (ROLE_ADMIN, ROLE_RECRUITER)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=True, default=ROLE_RECRUITER)  # NULL on pre-roles rows; treated as recruiter
    created_at = Column(DateTime, default=datetime.utcnow)
    positions = relationship("Position", back_populates="creator")
    batches = relationship("IngestionBatch", back_populates="creator")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


DEFAULT_DEMAND_NAMES = ("Java", "GenAI", "Camunda", "Pega", "Others")  # the five fixed categories
OTHERS_DEMAND_NAME = "Others"


def canonical_demand_id(name: str) -> str:
    return f"default-demand-{name.lower()}"


def demand_display_id(demand_id: Optional[str]) -> Optional[str]:
    """TRU-DM-01..05 for the five fixed demands (their position in DEFAULT_DEMAND_NAMES); None for anything else."""
    for i, name in enumerate(DEFAULT_DEMAND_NAMES, start=1):
        if canonical_demand_id(name) == demand_id:
            return f"TRU-DM-{i:02d}"
    return None


class Demand(Base):
    """A hiring demand that groups related requirements (Positions). Purely organisational: matching,
    scoring and candidate statuses stay per-Position, and a Position may exist without a Demand."""
    __tablename__ = "demands"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)  # NULL for system-seeded default demands
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    positions = relationship("Position", back_populates="demand", passive_deletes=True)


JD_STATUSES = ("Open", "Cancelled", "Fulfilled", "Mapped")  # lifecycle of a JD (Position)
# "Map" was renamed and "Closed" was removed (those demands are Cancelled); old rows and clients are still understood.
LEGACY_JD_STATUS_ALIASES = {"Map": "Mapped", "Closed": "Cancelled"}
INACTIVE_JD_STATUSES = ("Cancelled",)  # kept on record but not counted on demand folders
RESUME_LINKED_JD_STATUSES = ("Mapped", "Fulfilled")  # statuses that name the resume(s) the demand was filled with
MAX_CANCELLATION_REASON_CHARS = 1000
CLIENT_NAMES = ("Cretera", "Infosys", "Coforge", "Aaseya", "NTT Data", "Utsuk")  # the clients a demand can belong to
DEFAULT_JD_STATUS = "Open"


class Position(Base):
    __tablename__ = "positions"
    id = Column(String, primary_key=True, default=generate_uuid)
    display_id = Column(String, unique=True, index=True, nullable=True)
    title = Column(String, nullable=False, index=True)
    jd_text = Column(Text, nullable=False)
    jd_summary = Column(Text, nullable=True)
    jd_version = Column(Integer, default=1, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    file_url = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    # Location / role / work mode read from the JD, cached per jd_version so the LLM runs once per edit.
    search_filters = Column(JSON, nullable=True)
    # Optional grouping; NULL = standalone requirement. Deleting a Demand never deletes its positions.
    demand_id = Column(String, ForeignKey("demands.id", ondelete="SET NULL"), nullable=True, index=True)
    # JD details entered by the recruiter; NULL = not stated. status NULL on pre-status rows is treated as Open.
    status = Column(String, nullable=True, default=DEFAULT_JD_STATUS, index=True)
    role = Column(String, nullable=True)
    experience_years = Column(Float, nullable=True)  # minimum years required
    experience_max_years = Column(Float, nullable=True)
    no_of_positions = Column(Integer, nullable=True)  # how many hires the demand is for; NULL on demands made before this field
    locations = Column(JSON, nullable=True)  # list of places; `location` below mirrors it as "; "-joined text
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    location = Column(String, nullable=True)
    client_name = Column(String, nullable=True)  # optional; NULL = not stated
    updated_at = Column(DateTime, nullable=True)  # last modified; NULL = never changed since creation
    updated_by = Column(String, nullable=True)  # user id of the last modifier; NULL = unknown / never changed
    cancellation_reason = Column(Text, nullable=True)  # only while status is Cancelled
    mapped_candidate_ids = Column(JSON, nullable=True)  # candidate ids the demand is Mapped / Fulfilled with
    creator = relationship("User", back_populates="positions")
    demand = relationship("Demand", back_populates="positions")
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
    # Live progress: overall stage (queued/reading/embedding/indexing/done) and one entry per
    # file {filename, status, detail} with status queued/extracting/analyzing/embedding/indexing/indexed/duplicate/failed.
    stage = Column(String, default="queued")
    file_status = Column(JSON, default=list)
    creator = relationship("User", back_populates="batches")
    candidates = relationship("Candidate", back_populates="batch")


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(String, primary_key=True, default=generate_uuid)
    display_id = Column(String, unique=True, index=True, nullable=True)
    position_id = Column(String, ForeignKey("positions.id"), nullable=True)
    resume_file_url = Column(String, nullable=True)
    candidate_name = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    extracted_skills = Column(JSON, default=list)
    years_experience = Column(Float, default=0.0)
    education = Column(Text, nullable=True)
    # Extracted only when the resume states them; NULL/[] means unknown, never a guess.
    location = Column(String, nullable=True)
    location_norm = Column(String, nullable=True)   # '|bengaluru|karnataka|india|' (see retrieval/filters.py)
    job_titles = Column(JSON, default=list)         # most recent first
    title_norms = Column(String, nullable=True)
    resume_text = Column(Text, nullable=True)
    pii_detected = Column(JSON, default=dict)
    status = Column(String, default="New", index=True)
    status_updated_by = Column(String, nullable=True)
    status_updated_at = Column(DateTime, nullable=True)
    # Notice period as stated by the recruiter: a non-negative number plus a unit (see NOTICE_PERIOD_UNITS).
    notice_period_value = Column(Float, nullable=True)
    notice_period_unit = Column(String, nullable=True)
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
    location = Column(String, nullable=True)
    role = Column(String, nullable=True)
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


CANDIDATE_STATUSES = ("New", "Shortlisted", "Interviewed", "Rejected")  # global pipeline stage of a candidate
REQUIREMENT_STATUSES = ("Pending Review", "Shortlisted", "Not Shortlisted")
DEFAULT_REQUIREMENT_STATUS = "Pending Review"


class RequirementCandidateStatus(Base):
    """Recruiter review status of one candidate for one requirement; independent of Candidate.status."""
    __tablename__ = "requirement_candidate_statuses"
    id = Column(String, primary_key=True, default=generate_uuid)
    position_id = Column(String, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default=DEFAULT_REQUIREMENT_STATUS)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("position_id", "candidate_id", name="uq_requirement_candidate_status"),)


class CandidateAssignment(Base):
    """Which recruiter reviews a candidate for a requirement. One assignee per (requirement, candidate)."""
    __tablename__ = "candidate_assignments"
    id = Column(String, primary_key=True, default=generate_uuid)
    position_id = Column(String, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("position_id", "candidate_id", name="uq_candidate_assignment"),)


class CandidateComment(Base):
    """Shared review feedback on a candidate, optionally scoped to one requirement. Visible to every user."""
    __tablename__ = "candidate_comments"
    id = Column(String, primary_key=True, default=generate_uuid)
    candidate_id = Column(String, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id = Column(String, ForeignKey("positions.id", ondelete="CASCADE"), nullable=True, index=True)
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)  # 1-5, optional
    created_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime, nullable=True)
    author = relationship("User", foreign_keys=[author_id])


EMAIL_STATUS_SENT = "sent"
EMAIL_STATUS_SIMULATED = "simulated"
EMAIL_STATUS_FAILED = "failed"


NOTICE_PERIOD_UNITS = ("Days", "Weeks", "Months")

HISTORY_CREATED, HISTORY_UPDATED, HISTORY_DELETED, HISTORY_STATUS_CHANGED = "created", "updated", "deleted", "status_changed"
HISTORY_ACTIONS = (HISTORY_CREATED, HISTORY_UPDATED, HISTORY_STATUS_CHANGED, HISTORY_DELETED)


class RequirementHistory(Base):
    """Append-only audit trail of demand/JD changes. Item and user fields are snapshots so entries
    survive deletion of the JD or the user; `changes` maps field -> {old, new} where applicable."""
    __tablename__ = "requirement_history"
    id = Column(String, primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    item_type = Column(String, nullable=False, default="jd")  # jd | demand
    item_id = Column(String, nullable=True, index=True)
    item_display_id = Column(String, nullable=True)
    item_title = Column(String, nullable=True)
    demand_id = Column(String, nullable=True, index=True)
    demand_display_id = Column(String, nullable=True)
    demand_name = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    changes = Column(JSON, nullable=True)


class EmailRecord(Base):
    """Email history. Role/candidate fields are snapshots so history survives requirement or candidate deletion."""
    __tablename__ = "email_records"
    id = Column(String, primary_key=True, default=generate_uuid)
    position_id = Column(String, nullable=True, index=True)
    position_display_id = Column(String, nullable=True)
    position_title = Column(String, nullable=True)
    candidate_id = Column(String, nullable=True, index=True)
    candidate_display_id = Column(String, nullable=True)
    candidate_name = Column(String, nullable=True)
    recipient_email = Column(String, nullable=False)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, index=True)
    delivery_mode = Column(String, nullable=False)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=1)
    idempotency_key = Column(String, nullable=True, unique=True)
    sent_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIAuditEvent(Base):
    """One row per AI model call, guardrail verdict or AI-driven screening decision.

    Prompts and outputs are stored only as PII-redacted, truncated previews plus a hash
    of the full prompt, so the trail is reviewable without becoming a second resume store.
    """
    __tablename__ = "ai_audit_events"
    id = Column(String, primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    trace_id = Column(String, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    feature = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)  # ok | error | blocked
    prompt_sha256 = Column(String, nullable=True)
    prompt_preview = Column(Text, nullable=True)
    output_preview = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    details = Column(JSON, nullable=True)  # guardrail verdicts, screening reasons, etc.
    error = Column(Text, nullable=True)


class IdSequence(Base):
    """Monotonic counters for human-readable display IDs; numbers are never reused after deletion."""
    __tablename__ = "id_sequences"
    name = Column(String, primary_key=True)
    value = Column(Integer, nullable=False, default=0)


POSITION_ID_PREFIX = "DM-"
CANDIDATE_ID_PREFIX = "TRU-CN-"


def _max_existing_display_number(db, model, prefix: str) -> int:
    import re
    max_num = 0
    for (d_id,) in db.query(model.display_id).filter(model.display_id.like(f"{prefix}%")).all():
        m = re.fullmatch(rf"{re.escape(prefix)}(\d+)", d_id or "")
        if m:
            max_num = max(max_num, int(m.group(1)))
    return max_num


def seed_id_sequence(db, model, prefix: str) -> None:
    """Create the counter row if missing, starting after the highest ID already issued."""
    if db.query(IdSequence).filter(IdSequence.name == prefix).first() is None:
        db.add(IdSequence(name=prefix, value=_max_existing_display_number(db, model, prefix)))
        db.flush()


def _next_display_id(db, model, prefix: str) -> str:
    # The atomic UPDATE takes the write lock, so concurrent sessions cannot draw the same number.
    updated = db.query(IdSequence).filter(IdSequence.name == prefix).update(
        {IdSequence.value: IdSequence.value + 1}, synchronize_session=False
    )
    if not updated:
        seed_id_sequence(db, model, prefix)
        db.query(IdSequence).filter(IdSequence.name == prefix).update(
            {IdSequence.value: IdSequence.value + 1}, synchronize_session=False
        )
    value = db.query(IdSequence.value).filter(IdSequence.name == prefix).scalar()
    return f"{prefix}{value:04d}"


def get_next_position_display_id(db) -> str:
    return _next_display_id(db, Position, POSITION_ID_PREFIX)


def get_next_candidate_display_id(db) -> str:
    return _next_display_id(db, Candidate, CANDIDATE_ID_PREFIX)
