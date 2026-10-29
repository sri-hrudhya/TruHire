import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import SessionLocal, get_db
from backend.models import Conversation, ConversationMessage, DEFAULT_DEMAND_NAMES, Position, User, canonical_demand_id
from backend.routers.ingestion import process_batch
from backend.routers.job_descriptions import PositionCreateRequest, create_jd
from backend.services.classification import classify_jd_detailed
from backend.services.ingestion.parsing import extract_text_from_file, is_supported_jd_file
from backend.services.ingestion.storage import save_upload_file
from backend.services.llm.ai_service import untrusted
from backend.services.llm.router import chat_completion
from backend.services.retrieval.search import execute_candidate_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["assistant"])

_JD_ID = re.compile(r"\bTRU-JD-\d+\b", re.I)


class AssistantMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    conversation_id: Optional[str] = None
    position_id: Optional[str] = None


class AssistantConfirmJDRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    jd_text: str = Field(..., min_length=1, max_length=100000)
    demand_id: str
    position_count: Optional[int] = Field(default=None, ge=0, le=10000)
    role: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=2000)
    experience_years: Optional[float] = Field(default=None, ge=0, le=60)
    file_url: Optional[str] = None
    original_filename: Optional[str] = None


def _conversation(db: Session, user: User, conversation_id: Optional[str]) -> Conversation:
    if conversation_id:
        found = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        ).first()
        if found:
            return found
    conversation = Conversation(user_id=user.id, title="TruHire Assistant")
    db.add(conversation)
    db.flush()
    return conversation


def _save_message(
    db: Session,
    conversation: Conversation,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    db.add(ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content[:20000],
        message_data=metadata or {},
    ))


def _find_position(db: Session, message: str, position_id: Optional[str]) -> Optional[Position]:
    if position_id:
        found = db.query(Position).filter(Position.id == position_id).first()
        if found:
            return found
    display_id = _JD_ID.search(message or "")
    if display_id:
        found = db.query(Position).filter(Position.display_id.ilike(display_id.group(0))).first()
        if found:
            return found
    terms = [t.lower() for t in re.findall(r"[a-z0-9]{3,}", message or "") if t.lower() not in {
        "show", "find", "candidates", "candidate", "matches", "match", "for", "the", "jd", "job", "description",
        "draft", "email", "emails", "write", "suggest", "please", "top",
    }]
    if not terms:
        return None
    positions = db.query(Position).order_by(Position.created_at.desc()).all()
    ranked = sorted(
        positions,
        key=lambda p: sum(term in f"{p.title} {p.jd_text}".lower() for term in terms),
        reverse=True,
    )
    return ranked[0] if ranked and sum(term in f"{ranked[0].title} {ranked[0].jd_text}".lower() for term in terms) else None


def _position_choices(db: Session) -> List[dict]:
    return [
        {"id": p.id, "display_id": p.display_id, "title": p.title, "no_of_positions": p.no_of_positions or 1}
        for p in db.query(Position).order_by(Position.created_at.desc()).limit(50).all()
    ]


def _json_reply(messages: List[Dict[str, str]]) -> str:
    try:
        result = chat_completion(messages, temperature=0.1, max_tokens=700, enable_thinking=False)
        return result.strip()
    except Exception as exc:
        logger.warning("Assistant response generation failed: %s", exc)
        return ""


def _generic_reply(db: Session, request: AssistantMessageRequest, conversation: Conversation) -> str:
    history = [
        {"role": m.role, "content": m.content}
        for m in conversation.messages[-8:]
        if m.role in ("user", "assistant")
    ]
    positions = _position_choices(db)
    context = json.dumps(positions, ensure_ascii=True)
    prompt = (
        "You are the TruHire recruitment assistant. Help with resumes, demand documents, candidate matching, "
        "and email drafting. Never invent candidate facts. If the user asks to create a demand, ask for a fixed demand "
        "choice instead of creating it automatically. Keep answers concise and actionable.\n"
        f"Available requirements: {context}\n"
        f"User request: {untrusted('user_request', request.message)}"
    )
    reply = _json_reply([{"role": "system", "content": prompt}, *history])
    return reply or "I can ingest resumes or a demand document, create a demand after you choose its category, find the top candidates for a requirement, or prepare demand-grounded email drafts."


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(20).all()
    return {"conversations": [{"id": c.id, "title": c.title, "position_id": c.position_id, "candidate_id": c.candidate_id} for c in rows]}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    return {
        "id": conversation.id,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "data": m.message_data or {}}
            for m in conversation.messages
        ],
    }


@router.post("/message")
def assistant_message(
    request: AssistantMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, request.conversation_id)
    _save_message(db, conversation, "user", request.message)
    lower = request.message.lower()

    if any(term in lower for term in ("show candidates", "find candidates", "candidate matches", "matching candidates", "top candidates")):
        position = _find_position(db, request.message, request.position_id)
        if not position:
            reply = "Which requirement should I use? Select one below or mention its TRU-JD ID."
            data = {"action": "choose_position", "positions": _position_choices(db)}
        else:
            limit = max(1, min(int(position.no_of_positions or 1), 100))
            result = execute_candidate_search(db, position_id=position.id, top_n=limit)
            reply = f"I found the top {limit} candidate{'s' if limit != 1 else ''} for {position.display_id} · {position.title}, matching the demand strictly."
            data = {"action": "matches", "position": {"id": position.id, "display_id": position.display_id, "title": position.title, "no_of_positions": limit}, "results": result.get("results", []), "total_matches": result.get("total_matches", 0)}
    elif any(term in lower for term in ("draft email", "email suggestion", "suggest an email", "write email")):
        position = _find_position(db, request.message, request.position_id)
        if not position:
            reply = "Which requirement should the email follow? Select one below."
            data = {"action": "choose_position", "positions": _position_choices(db)}
        else:
            reply = f"I selected {position.display_id} · {position.title}. Open Email to review demand-grounded drafts; nothing will be sent automatically."
            data = {"action": "email", "position_id": position.id, "position": {"display_id": position.display_id, "title": position.title}}
    elif len(request.message) > 180 or "job description" in lower or "create a jd" in lower or "create demand" in lower:
        title = next((line.strip() for line in request.message.splitlines() if line.strip()), "Uploaded Job Description")[:200]
        classification = classify_jd_detailed(title, request.message)
        reply = "I read the demand document. Before I create it, choose exactly one demand category. I will not auto-assign it."
        data = {
            "action": "confirm_jd",
            "draft": {"title": title, "jd_text": request.message, "role": None, "location": None, "experience_years": None, "position_count": 1},
            "suggested_demand": classification.category if classification.confident else None,
            "demands": [{"id": canonical_demand_id(name), "name": name} for name in DEFAULT_DEMAND_NAMES],
        }
    else:
        reply = _generic_reply(db, request, conversation)
        data = {"action": "reply"}

    _save_message(db, conversation, "assistant", reply, data)
    conversation.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"conversation_id": conversation.id, "reply": reply, **data}


@router.post("/confirm-jd")
def confirm_jd(request: AssistantConfirmJDRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if request.demand_id not in {canonical_demand_id(name) for name in DEFAULT_DEMAND_NAMES}:
        raise HTTPException(422, "Choose one of: " + ", ".join(DEFAULT_DEMAND_NAMES) + ".")
    created = create_jd(PositionCreateRequest(
        title=request.title,
        jd_text=request.jd_text,
        demand_id=request.demand_id,
        no_of_positions=request.position_count if request.position_count is not None else 1,
        role=request.role,
        location=request.location,
        experience_years=request.experience_years,
        file_url=request.file_url,
        original_filename=request.original_filename,
    ), db, user)
    return {"action": "created", "position": {"id": created.id, "display_id": created.display_id, "title": created.title, "demand_id": created.demand_id, "no_of_positions": created.no_of_positions}, "message": f"Created {created.display_id} · {created.title} in the selected demand."}


@router.post("/upload")
async def assistant_upload(
    file: UploadFile = File(...),
    kind: str = Form("auto"),
    conversation_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filename = file.filename or "uploaded-document"
    content = await file.read()
    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    if kind not in ("auto", "jd", "resume"):
        raise HTTPException(422, "kind must be auto, jd, or resume.")
    conversation = _conversation(db, user, conversation_id)
    _save_message(db, conversation, "user", f"Uploaded demand/resume file: {filename}")
    is_jd = kind == "jd" or (kind == "auto" and "jd" in filename.lower())
    if is_jd:
        if not is_supported_jd_file(filename):
            raise HTTPException(400, "Unsupported demand document type.")
        text = extract_text_from_file(filename, content).strip()
        if not text:
            raise HTTPException(400, "No readable text found in the uploaded demand document.")
        file_url, _ = save_upload_file(filename, content, category="job_descriptions")
        title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:200] or "Uploaded Job Description"
        classification = classify_jd_detailed(title, text)
        data = {"action": "confirm_jd", "reply": f"I received and read “{filename}”. Choose a demand category before I create it.", "draft": {"title": title, "jd_text": text, "file_url": file_url, "original_filename": filename, "position_count": 1}, "suggested_demand": classification.category if classification.confident else None, "demands": [{"id": canonical_demand_id(name), "name": name} for name in DEFAULT_DEMAND_NAMES]}
        _save_message(db, conversation, "assistant", data["reply"], data)
        conversation.updated_at = __import__("datetime").datetime.utcnow()
        db.commit()
        return {"conversation_id": conversation.id, **data}
    if not background_tasks:
        raise HTTPException(500, "Background task runner is unavailable.")
    from backend.models import IngestionBatch, generate_uuid
    batch = IngestionBatch(id=generate_uuid(), created_by=user.id, total_files=1, status="processing", stage="queued", file_status=[{"filename": filename, "status": "queued", "detail": ""}])
    db.add(batch)
    db.commit()
    background_tasks.add_task(process_batch, batch.id, [(filename, content)], user.id)
    data = {"action": "resume_ingestion", "reply": f"I received “{filename}”. Resume ingestion has started; you can monitor it in Ingestion History.", "batch_id": batch.id}
    _save_message(db, conversation, "assistant", data["reply"], data)
    conversation.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"conversation_id": conversation.id, **data}
