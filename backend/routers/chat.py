from datetime import datetime
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Candidate, Position, User, Conversation, ConversationMessage
from backend.auth import get_current_user
from backend.services.llm.rag import build_candidate_context, build_jd_context, ask_rag_question
from backend.services.llm import decision
from backend.services.llm.guardrails import check_chat_reply, check_decision_reply
from backend.services.llm.laya_service import LayaUnavailable
from backend.services.common.ai_audit import ai_feature

router = APIRouter(prefix="/api/chat", tags=["chat"])
class ChatMessage(BaseModel):
    # 'system' is never accepted from a client: that would let a user rewrite the assistant's instructions.
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)
class ChatRequest(BaseModel): messages: List[ChatMessage] = []; candidate_id: Optional[str] = None; position_id: Optional[str] = None; conversation_id: Optional[str] = None

@router.post("")
def chat_with_rag(req: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not req.messages: raise HTTPException(status_code=400, detail="Messages cannot be empty.")
    conversation = None
    if req.conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == req.conversation_id, Conversation.user_id == user.id).first()
        if not conversation: raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        if req.candidate_id and not db.query(Candidate).filter(Candidate.id == req.candidate_id).first(): raise HTTPException(status_code=404, detail="Candidate not found.")
        if req.position_id and not db.query(Position).filter(Position.id == req.position_id).first(): raise HTTPException(status_code=404, detail="Job description not found.")
        conversation = Conversation(user_id=user.id, candidate_id=req.candidate_id, position_id=req.position_id, title=req.messages[-1].content[:80])
        db.add(conversation); db.flush()

    # Persist only new incoming messages. The frontend sends the latest user
    # message, while the DB remains the source of truth for conversation memory.
    # Only user turns are taken from the client; assistant turns are always the server's own
    # stored replies, so a client can't fabricate prior assistant answers either.
    for msg in req.messages:
        if msg.role == "user":
            db.add(ConversationMessage(conversation_id=conversation.id, role=msg.role, content=msg.content))
    conversation.updated_at = datetime.utcnow()
    db.commit(); db.refresh(conversation)

    if conversation.candidate_id:
        cand = db.query(Candidate).filter(Candidate.id == conversation.candidate_id).first(); context = build_candidate_context(cand, db); context_type = f"candidate:{cand.id}"
    elif conversation.position_id:
        pos = db.query(Position).filter(Position.id == conversation.position_id).first(); context = build_jd_context(pos); context_type = f"position:{pos.id}"
    else:
        context = "TruHire recruitment assistant. No specific candidate or JD was selected."; context_type = "general"

    # Pre-flight: classify the question with Laya before touching the LLM. Judgment-style
    # questions ("should I interview this candidate") get answered directly from Laya's
    # own typed decision when it's confident; anything else (or a low-confidence/escalated
    # Laya call) falls back to the existing RAG chat path unchanged.
    latest_user_message = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    intent = decision.classify_chat_intent(latest_user_message) if latest_user_message else "open_qa"

    reply = None
    is_laya_decision = False
    if intent == "interview_decision" and conversation.candidate_id:
        jd_context = context
        if cand.position_id:
            linked_position = db.query(Position).filter(Position.id == cand.position_id).first()
            if linked_position:
                jd_context = build_jd_context(linked_position)
        try:
            laya_decision = decision.decide_interview(context, jd_context)
            if not laya_decision.should_escalate:
                verdict = "suggests interviewing" if laya_decision.answer else "does not suggest interviewing"
                reply = (
                    f"AI suggestion: the model {verdict} this candidate (confidence {laya_decision.probability:.0%}). "
                    "This is decision support only - a recruiter must make the final decision."
                )
                is_laya_decision = True
        except LayaUnavailable:
            pass

    if reply is None:
        history = [{"role": m.role, "content": m.content} for m in conversation.messages]
        reply = ask_rag_question(history, context)

    # A Laya-direct decision is a judgment statement, not a claim from context - only
    # the safety check applies (see check_decision_reply's docstring).
    with ai_feature("interview_decision" if is_laya_decision else "chat"):
        guard = check_decision_reply(reply) if is_laya_decision else check_chat_reply(reply, context)
    if not guard.passed:
        reply = "I couldn't verify this answer against the available candidate/JD data — please review this one manually."

    db.add(ConversationMessage(conversation_id=conversation.id, role="assistant", content=reply)); db.commit()
    return {"reply": reply, "context_type": context_type, "conversation_id": conversation.id, "intent": intent}

@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).all()
    return {"conversations": [{"id": c.id, "title": c.title, "candidate_id": c.candidate_id, "position_id": c.position_id, "created_at": c.created_at, "updated_at": c.updated_at} for c in rows]}

@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not c: raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": c.id, "title": c.title, "candidate_id": c.candidate_id, "position_id": c.position_id, "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in c.messages]}
