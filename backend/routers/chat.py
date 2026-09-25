from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Candidate, Position, User, Conversation, ConversationMessage
from backend.auth import get_current_user
from backend.services.rag import build_candidate_context, build_jd_context, ask_rag_question

router = APIRouter(prefix="/api/chat", tags=["chat"])
class ChatMessage(BaseModel): role: str; content: str
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
    if req.conversation_id:
        for msg in req.messages:
            if msg.role == "user":
                db.add(ConversationMessage(conversation_id=conversation.id, role=msg.role, content=msg.content))
    else:
        for msg in req.messages:
            db.add(ConversationMessage(conversation_id=conversation.id, role=msg.role, content=msg.content))
    conversation.updated_at = __import__("datetime").datetime.utcnow()
    db.commit(); db.refresh(conversation)

    if conversation.candidate_id:
        cand = db.query(Candidate).filter(Candidate.id == conversation.candidate_id).first(); context = build_candidate_context(cand, db); context_type = f"candidate:{cand.id}"
    elif conversation.position_id:
        pos = db.query(Position).filter(Position.id == conversation.position_id).first(); context = build_jd_context(pos); context_type = f"position:{pos.id}"
    else:
        context = "TruHire recruitment assistant. No specific candidate or JD was selected."; context_type = "general"

    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    reply = ask_rag_question(history, context)
    db.add(ConversationMessage(conversation_id=conversation.id, role="assistant", content=reply)); db.commit()
    return {"reply": reply, "context_type": context_type, "conversation_id": conversation.id}

@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).all()
    return {"conversations": [{"id": c.id, "title": c.title, "candidate_id": c.candidate_id, "position_id": c.position_id, "created_at": c.created_at, "updated_at": c.updated_at} for c in rows]}

@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not c: raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"id": c.id, "title": c.title, "candidate_id": c.candidate_id, "position_id": c.position_id, "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in c.messages]}
