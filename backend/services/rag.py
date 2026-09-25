from typing import List, Dict
from sqlalchemy.orm import Session
from backend.models import Candidate, Position, CandidateMatch
from backend.services.pii import redact_pii
from backend.services.ai_service import answer_chat_query


def build_candidate_context(candidate: Candidate, db: Session) -> str:
    matches = db.query(CandidateMatch).filter(CandidateMatch.candidate_id == candidate.id).all()
    match_info = []
    for m in matches:
        pos = db.query(Position).filter(Position.id == m.position_id).first()
        match_info.append(f"- Position: {pos.title if pos else 'Unknown'}, Score: {m.match_score}%, Summary: {m.llm_summary or ''}")
    return redact_pii(f"""Candidate: {candidate.candidate_name}\nSkills: {', '.join(candidate.extracted_skills or [])}\nExperience: {candidate.years_experience} years\nEducation: {candidate.education or 'Not specified'}\nStatus: {candidate.status}\nResume text:\n{candidate.resume_text or ''}\nEvaluated matches:\n{chr(10).join(match_info) or 'None'}""", candidate_name=candidate.candidate_name)


def build_jd_context(position: Position) -> str:
    return redact_pii(f"Job Title: {position.title}\nVersion: {position.jd_version}\nSummary: {position.jd_summary or ''}\nDescription:\n{position.jd_text}")


def ask_rag_question(messages: List[Dict[str, str]], context: str) -> str:
    return answer_chat_query(messages, context)
