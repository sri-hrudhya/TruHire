from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Candidate, Position, User
from backend.auth import get_current_user
from backend.services.rag import build_candidate_context, build_jd_context, ask_rag_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str  # 'user', 'assistant', 'system'
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    candidate_id: Optional[str] = None
    position_id: Optional[str] = None


@router.post("")
def chat_with_rag(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    RAG-powered conversational assistant for Q&A over a candidate profile or job description.
    """
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty.")

    context = ""
    context_type = "general"
    cache_prefix = "chat"

    if req.candidate_id:
        cand = db.query(Candidate).filter(Candidate.id == req.candidate_id).first()
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        context = build_candidate_context(cand, db)
        context_type = f"candidate:{cand.id}"
        cache_prefix = f"chat_cand_{cand.id}"

    elif req.position_id:
        pos = db.query(Position).filter(Position.id == req.position_id).first()
        if not pos:
            raise HTTPException(status_code=404, detail="Job description not found.")
        context = build_jd_context(pos)
        context_type = f"position:{pos.id}"
        cache_prefix = f"chat_pos_{pos.id}"

    else:
        context = "TruHire AI Assistant: General recruitment knowledge and platform assistant."

    messages_payload = [{"role": m.role, "content": m.content} for m in req.messages]
    reply = ask_rag_question(messages_payload, context, cache_prefix=cache_prefix)

    return {
        "reply": reply,
        "context_type": context_type
    }
