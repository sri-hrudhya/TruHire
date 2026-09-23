import hashlib
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Candidate, Position, CandidateMatch
from backend.services.pii import redact_pii
from backend.services.ai_service import answer_chat_query
from backend.services.cache import get_cache, set_cache


def build_candidate_context(candidate: Candidate, db: Session) -> str:
    """Builds redacted candidate profile context for RAG."""
    # Retrieve all matches for this candidate
    matches = db.query(CandidateMatch).filter(CandidateMatch.candidate_id == candidate.id).all()
    match_info = []
    for m in matches:
        pos = db.query(Position).filter(Position.id == m.position_id).first()
        pos_title = pos.title if pos else "Unknown Position"
        match_info.append(f"- Position: {pos_title}, Match Score: {m.match_score}%, Summary: {m.llm_summary}")

    context = f"""
Candidate Name: {candidate.candidate_name}
Skills: {", ".join(candidate.extracted_skills or [])}
Experience: {candidate.years_experience} years
Education: {candidate.education or 'Not specified'}
Status: {candidate.status}
Evaluated Job Matches:
{chr(10).join(match_info) if match_info else 'No evaluated positions yet.'}
"""
    return redact_pii(context, candidate_name=candidate.candidate_name)


def build_jd_context(position: Position) -> str:
    """Builds JD context for RAG."""
    context = f"""
Job Title: {position.title}
Version: {position.jd_version}
Summary: {position.jd_summary or 'No summary generated yet.'}
Description:
{position.jd_text}
"""
    return redact_pii(context)


def ask_rag_question(
    messages: List[Dict[str, str]],
    context: str,
    cache_prefix: str = "chat"
) -> str:
    """Executes RAG Q&A with caching."""
    # Cache key based on last message and context hash
    last_msg = messages[-1]["content"] if messages else ""
    cache_key = f"{cache_prefix}_{hashlib.md5((last_msg + context).encode('utf-8')).hexdigest()}"

    cached = get_cache(cache_key)
    if cached:
        return cached

    response = answer_chat_query(messages, context)
    set_cache(cache_key, response, settings.CACHE_TTL_CHAT)
    return response
