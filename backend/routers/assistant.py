import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import SessionLocal, get_db
from backend.models import Conversation, ConversationMessage, Position, User
from backend.routers import assistant_demand
from backend.routers.ingestion import process_batch
from backend.services.ingestion.doc_kind import detect_document_kind
from backend.services.ingestion.parsing import YEARS_EXP_PATTERN, extract_text_from_file, is_supported_jd_file
from backend.services.ingestion.storage import save_upload_file
from backend.services.llm.ai_service import untrusted
from backend.services.llm.assistant_context import GLOSSARY, RULES, build_data_context
from backend.services.llm.router import chat_completion, chat_completion_stream
from backend.services.llm.scope import GREETING_REPLY, REFUSAL, SCOPE_RULE, is_greeting, is_in_scope
from backend.services.common import ai_audit
from backend.services.retrieval.search import execute_candidate_search
from backend.services.retrieval.filters import extract_jd_filters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["assistant"])

_JD_ID = re.compile(r"\bTRU-JD-\d+\b", re.I)
HISTORY_MESSAGES = 6  # recent turns sent to the model; older ones are not needed to follow the thread
HISTORY_MESSAGE_CHARS = 1500


class AssistantMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    conversation_id: Optional[str] = None
    position_id: Optional[str] = None


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
        {"id": p.id, "display_id": p.display_id, "title": p.title, "no_of_positions": p.no_of_positions or 1,
         "client_name": p.client_name, "demand_id": p.demand_id, "demand_name": p.demand.name if p.demand else None}
        for p in db.query(Position).order_by(Position.created_at.desc()).limit(50).all()
    ]


def _client_demand_action(db: Session, message: str) -> Optional[tuple]:
    lower = message.lower()
    browse_intent = any(phrase in lower for phrase in (
        "by client", "client names", "show clients", "list clients", "group clients",
        "show demands", "list demands", "demands for", "requirements for", "show requirements", "list requirements",
        "show positions", "list positions",
    ))
    if "client" not in lower or not browse_intent:
        return None
    positions = db.query(Position).order_by(Position.created_at.desc()).all()
    if not positions:
        return "I couldn't find any saved demands yet.", {"action": "client_groups", "clients": []}
    demand_names = sorted({p.demand.name for p in positions if p.demand and p.demand.name}, key=len, reverse=True)
    demand_filter = next((name for name in demand_names if name.lower() in lower), None)
    if demand_filter:
        positions = [p for p in positions if p.demand and p.demand.name.lower() == demand_filter.lower()]
    client_names = sorted({(p.client_name or "").strip() for p in positions if (p.client_name or "").strip()}, key=len, reverse=True)
    client_filter = next((name for name in client_names if name.lower() in lower), None)

    def serialize(p):
        return {"id": p.id, "display_id": p.display_id, "title": p.title, "client_name": p.client_name,
                "demand_id": p.demand_id, "demand_name": p.demand.name if p.demand else None}

    if client_filter:
        matches = [serialize(p) for p in positions if (p.client_name or "").strip().lower() == client_filter.lower()]
        if not matches:
            return f"I couldn't find demands for {client_filter}" + (f" in {demand_filter}." if demand_filter else "."), {"action": "client_demands", "client_name": client_filter, "requirements": []}
        return f"Here are the demands for {client_filter}" + (f" in {demand_filter}." if demand_filter else "."), {"action": "client_demands", "client_name": client_filter, "requirements": matches}

    grouped = {}
    for position in positions:
        name = (position.client_name or "").strip() or "No client assigned"
        grouped.setdefault(name, []).append(serialize(position))
    clients = [{"name": name, "count": len(requirements), "requirements": requirements}
               for name, requirements in sorted(grouped.items(), key=lambda item: (item[0] == "No client assigned", item[0].casefold()))]
    scope = f" in {demand_filter}" if demand_filter else ""
    return f"I grouped the demands by client{scope}. Select a client to see its requirements.", {"action": "client_groups", "demand_name": demand_filter, "clients": clients}


def _demand_count_action(db: Session, message: str) -> Optional[tuple]:
    """Answer count questions about saved demand/requirement records, optionally scoped by a name."""
    lower = (message or "").lower()
    asks_count = re.search(r"\b(how\s+many|number\s+of|count(?:\s+of)?)\b", lower)
    names_records = re.search(r"\b(demands?|requirements?|job\s+descriptions?|jds?)\b", lower)
    if not asks_count or not names_records:
        return None
    if re.search(r"\b(practices?|clients?|per|each|breakdown|group(?:ed)?)\b", lower):
        return None  # a breakdown or a practice/client question: the model answers from the full counts

    stop = {
        "how", "many", "number", "of", "count", "the", "are", "is", "there", "in", "on", "for",
        "present", "available", "saved", "currently", "total", "please", "can", "you", "check", "tell",
        "me", "show", "all", "what", "within", "under", "by", "and", "or", "a", "an", "demand",
        "demands", "requirement", "requirements", "job", "description", "descriptions", "jd", "jds",
    }
    terms = [term for term in re.findall(r"[a-z0-9]+", lower) if term not in stop]
    positions = db.query(Position).order_by(Position.created_at.desc()).all()
    matches = []
    for position in positions:
        indexed = " ".join((position.title or "", position.client_name or "", position.demand.name if position.demand else "", position.jd_text or "")).lower()
        if not terms or all(term in indexed for term in terms):
            matches.append(position)

    if terms:
        scope = " ".join(terms)
        noun = f"matching “{scope}”"
    else:
        scope = None
        noun = "in total"
    count = len(matches)
    if count == 0:
        reply = f"I couldn’t find any saved demands {noun}."
    else:
        sample = "; ".join(f"{p.display_id or 'JD'} · {p.title}" for p in matches[:8])
        suffix = f" Examples: {sample}." if sample else ""
        reply = f"There {'is' if count == 1 else 'are'} {count} saved demand{'s' if count != 1 else ''} {noun}.{suffix}"
    return reply, {"action": "demand_count", "count": count, "query": scope,
                   "requirements": [{"id": p.id, "display_id": p.display_id, "title": p.title} for p in matches]}


def _jd_field_report(title: str, text: str) -> dict:
    """Extract only values stated in the JD and explicitly list fields that were not found."""
    filters = extract_jd_filters(title or "", text or "")
    exp = [float(value) for value in YEARS_EXP_PATTERN.findall(text or "")]
    exp_range = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b", text or "", re.I)
    stated_count = re.search(r"\b(\d{1,4})\s+(?:openings?|positions?|vacanc(?:y|ies)|resources?)\b", text or "", re.I)
    stated_client = re.search(r"\b(?:client|customer)(?:\s+name)?\s*[:\-]\s*([^\n,;]{2,100})", text or "", re.I)
    start_date = _extract_labeled_date(text, r"start(?:ing)?\s+date|joining\s+date")
    end_date = _extract_labeled_date(text, r"(?:tentative\s+)?end\s+date|contract\s+end|assignment\s+end")
    stated_role = filters.get("role") if (filters.get("sources") or {}).get("role") == "jd_text" else None
    skill_section = re.search(
        r"(?:required\s+skills?|technical\s+skills?|skills\s*(?:and\s*qualifications)?|qualifications?|requirements?)\s*[:\-]?\s*\n(.*?)(?=\n\s*(?:[A-Z][A-Z /&-]{2,}|responsibilities|what you will|about the role)\s*[:\-]?\s*$|\Z)",
        text or "", re.I | re.S,
    )
    skill_lines = []
    if skill_section:
        chunks = re.split(r"[,;\n•]+", skill_section.group(1))
        for chunk in chunks:
            cleaned = re.sub(r"^\s*[-*•\d.)]+\s*", "", chunk).strip(" \t,;•.")
            if cleaned and len(cleaned) <= 70 and len(skill_lines) < 12:
                skill_lines.append(cleaned)
    fields = {
        "Job title": stated_role,
        "Client": stated_client.group(1).strip() if stated_client else None,
        "Location": filters.get("location"),
        "Experience": (f"{float(exp_range.group(1)):g}-{float(exp_range.group(2)):g} years" if exp_range else f"{max(exp):g}+ years" if exp else None),
        "Maximum experience": float(exp_range.group(2)) if exp_range else None,
        "Work mode": filters.get("work_mode"),
        "Number of positions": int(stated_count.group(1)) if stated_count else None,
        "Skills / qualifications": ", ".join(skill_lines) if skill_lines else None,
        "Start date": start_date,
        "End date": end_date,
    }
    present = [{"name": name, "value": str(value)} for name, value in fields.items() if value not in (None, "")]
    missing = [name for name, value in fields.items() if value in (None, "")]
    values = {
        "role": stated_role,
        "title": stated_role,
        "client_name": fields["Client"],
        "location": fields["Location"],
        "locations": [part.strip() for part in re.split(r"[,;|]", fields["Location"] or "") if part.strip()],
        "experience_years": float(exp_range.group(1)) if exp_range else (min(exp) if exp else None),
        "experience_max_years": float(exp_range.group(2)) if exp_range else None,
        "position_count": fields["Number of positions"],
        "work_mode": fields["Work mode"],
        "start_date": start_date,
        "end_date": end_date,
    }
    return {"present": present, "missing": missing, "values": values}


def _extract_labeled_date(text: str, label_pattern: str) -> Optional[str]:
    token = r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
    match = re.search(rf"\b(?:{label_pattern})\b\s*(?:is|on|:|=|-)?\s*{token}", text or "", re.I)
    if not match:
        return None
    raw = match.group(1).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
                "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _field_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return any(phrase in normalized for phrase in (
        "what fields", "which fields", "fields present", "fields missing", "missing fields", "not stated fields",
        "what is in the jd", "what's in the jd", "what does the jd", "check the jd fields", "jd field report",
    ))


def _field_report_for_request(db: Session, conversation: Conversation, request: AssistantMessageRequest) -> Optional[tuple]:
    """Resolve a JD field question to an explicit position, latest upload, or sole saved JD."""
    display_id = _JD_ID.search(request.message or "")
    position = db.query(Position).filter(Position.id == request.position_id).first() if request.position_id else None
    if not position and display_id:
        position = db.query(Position).filter(Position.display_id.ilike(display_id.group(0))).first()
    if not position:
        terms = {term.lower() for term in re.findall(r"[a-z0-9]{3,}", request.message or "")}
        stop = {"what", "which", "fields", "field", "missing", "present", "found", "stated", "extracted", "does", "this", "that", "the", "are", "for", "jd", "job", "description", "demand"}
        specific = terms - stop
        if specific:
            candidates = db.query(Position).order_by(Position.created_at.desc()).all()
            ranked = sorted(candidates, key=lambda p: sum(term in (p.title or "").lower() for term in specific), reverse=True)
            if ranked and sum(term in (ranked[0].title or "").lower() for term in specific) > 0:
                position = ranked[0]
    if position:
        report = _jd_field_report(position.title, position.jd_text or "")
        # Recruiter-entered values are useful saved fields even when the JD body omits them.
        explicit = {
            "Job title": position.role,
            "Client": position.client_name,
            "Location": position.location,
            "Experience": (f"{position.experience_years:g}+ years" if position.experience_years is not None else None),
            "Number of positions": position.no_of_positions,
        }
        _merge_report_values(report, explicit)
        ref = {"id": position.id, "display_id": position.display_id, "title": position.title}
    else:
        raw_upload = next((m.message_data for m in reversed(conversation.messages)
                           if m.role == "assistant" and (m.message_data or {}).get("action") == "confirm_jd"), None)
        if raw_upload:
            draft = raw_upload.get("draft") or {}
            report = raw_upload.get("field_report") or _jd_field_report(draft.get("title", ""), draft.get("jd_text", ""))
            ref = {"title": draft.get("title"), "filename": draft.get("original_filename")}
        else:
            positions = db.query(Position).order_by(Position.created_at.desc()).limit(2).all()
            if len(positions) != 1:
                if positions:
                    choices = _position_choices(db)
                    return "Which requirement should I inspect? Choose one by its ID:", {"action": "choose_position", "positions": choices}
                return None
            position = positions[0]
            report = _jd_field_report(position.title, position.jd_text or "")
            ref = {"id": position.id, "display_id": position.display_id, "title": position.title}
    title = ref.get("display_id") or ref.get("title") or "the uploaded JD"
    present = "; ".join(f"{item['name']}: {item['value']}" for item in report["present"]) or "No structured fields were confirmed."
    missing = ", ".join(report["missing"]) or "None of the tracked fields."
    reply = f"For {title}, I found: {present}. Not stated: {missing}."
    return reply, {"action": "field_report", "position": ref, "field_report": report}


def _merge_report_values(report: dict, values: dict) -> None:
    by_name = {item["name"]: item for item in report["present"]}
    for name, value in values.items():
        if value not in (None, ""):
            by_name[name] = {"name": name, "value": str(value)}
    report["present"] = list(by_name.values())
    report["missing"] = [name for name in report["missing"] if name not in by_name]


def _json_reply(messages: List[Dict[str, str]]) -> str:
    try:
        result = chat_completion(messages, temperature=0.1, max_tokens=700, enable_thinking=False)
        return result.strip()
    except Exception as exc:
        logger.warning("Assistant response generation failed: %s", exc)
        return ""


def _generic_messages(db: Session, request: AssistantMessageRequest, conversation: Conversation) -> List[Dict[str, str]]:
    history = [
        {"role": m.role, "content": m.content[:HISTORY_MESSAGE_CHARS]}
        for m in conversation.messages[-HISTORY_MESSAGES:]
        if m.role in ("user", "assistant")
    ]
    raw_upload = next((m.message_data for m in reversed(conversation.messages)
                          if m.role == "assistant" and (m.message_data or {}).get("action") == "confirm_jd"), None)
    recent_upload = None
    if raw_upload:
        draft = raw_upload.get("draft") or {}
        recent_upload = {"title": draft.get("title"), "filename": draft.get("original_filename"),
                         "field_report": raw_upload.get("field_report"), "jd_text": (draft.get("jd_text") or "")[:4000]}
    data = build_data_context(db, request.message, request.position_id)
    if recent_upload:
        data["most_recent_uploaded_jd"] = recent_upload
    prompt = (
        "You are the TruHire recruitment assistant. Help with resumes, demand documents, candidate matching, "
        "and email drafting. For field checks on a JD, separate fields explicitly found from fields not stated; "
        "never present a guess as extracted. Never invent candidate facts. If the user asks to create a demand, ask for a fixed demand "
        "choice instead of creating it automatically.\n"
        f"{GLOSSARY}\n{RULES}\n"
        f"{SCOPE_RULE}\n"
        f"DATA: {json.dumps(data, ensure_ascii=True, default=str)}\n"
        f"User request: {untrusted('user_request', request.message)}"
    )
    return [{"role": "system", "content": prompt}, *history]


_FALLBACK_REPLY = "I can ingest resumes or a demand document, create a demand after you choose its category, find the top candidates for a requirement, or prepare demand-grounded email drafts."


def _out_of_scope(request: AssistantMessageRequest, conversation: Conversation) -> bool:
    """Topic guardrail: True (and audited) when the message is not about TruHire or recruitment."""
    recent = [m.content for m in conversation.messages[-6:-1] if m.role == "user"]  # the last entry is the message being answered
    if is_in_scope(request.message, recent):
        return False
    ai_audit.record(provider="guardrail", status="blocked", feature="assistant_scope", prompt=request.message,
                    details={"check": "assistant_scope"})
    return True


def _generic_reply(db: Session, request: AssistantMessageRequest, conversation: Conversation) -> str:
    reply = _json_reply(_generic_messages(db, request, conversation))
    return reply or "I can ingest resumes or a demand document, create a demand after you choose its category, find the top candidates for a requirement, or prepare demand-grounded email drafts."


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(20).all()
    return {"conversations": [{"id": c.id, "title": c.title, "position_id": c.position_id, "candidate_id": c.candidate_id} for c in rows]}


@router.delete("/conversations")
def clear_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).all()
    count = len(rows)
    for conversation in rows:
        db.delete(conversation)
    db.commit()
    return {"deleted": count}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    session = assistant_demand.active_session(db, user, conversation.id)
    return {
        "id": conversation.id,
        "demand_session": assistant_demand.view(db, session) if session else None,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "data": m.message_data or {}}
            for m in conversation.messages
        ],
    }


def _route_message(db: Session, request: AssistantMessageRequest, user: User, conversation: Conversation) -> Optional[tuple]:
    """Deterministic assistant actions. Returns (reply, data), or None when the message is a free-text
    question that needs the LLM."""
    lower = request.message.lower()

    if is_greeting(request.message):
        return GREETING_REPLY, {"action": "reply"}

    client_action = _client_demand_action(db, request.message)
    if client_action:
        return client_action

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
    elif len(request.message) > 180 and detect_document_kind("", request.message) == "resume" and not any(
        phrase in lower for phrase in ("job description", "create a jd", "create demand")
    ):
        reply = "This looks like a resume. Attach the file with the paperclip and I will ingest it; I do not create demands from resumes."
        data = {"action": "reply"}
    elif assistant_demand.wants_new_demand(request.message) or (len(request.message) > 180 and is_in_scope(request.message)):
        # A short request starts the guided form; a long pasted JD starts it with the details read from the text.
        pasted = len(request.message) > 180
        session, messages = assistant_demand.begin(db, user, conversation, text=request.message if pasted else None, persist=False)
        reply = "\n\n".join(m["content"] for m in messages)
        data = {"action": "demand_session", "session": assistant_demand.view(db, session)}
    else:
        return None  # free-text question for the LLM
    return reply, data



def _finish(db: Session, conversation: Conversation, reply: str, data: dict) -> dict:
    _save_message(db, conversation, "assistant", reply, data)
    conversation.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return {"conversation_id": conversation.id, "reply": reply, **data}


@router.post("/message")
def assistant_message(
    request: AssistantMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, request.conversation_id)
    _save_message(db, conversation, "user", request.message)
    routed = _demand_count_action(db, request.message)
    if routed is None and _field_request(request.message):
        routed = _field_report_for_request(db, conversation, request)
    if routed is None:
        routed = _route_message(db, request, user, conversation)
    if routed is None:
        routed = (_generic_reply(db, request, conversation), {"action": "reply"})
    return _finish(db, conversation, *routed)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}" + chr(10) + "data: " + json.dumps(payload, ensure_ascii=False, default=str) + chr(10) * 2


@router.post("/message/stream")
def assistant_message_stream(
    request: AssistantMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Same as /message, but a free-text answer is sent as Server-Sent Events while the model writes it:
    `token` events carry text pieces, then one `done` event carries the final payload (same shape as
    /message). Deterministic actions skip straight to `done`. A failure after text has started arrives
    as an `error` event; the partial text is still saved."""
    conversation = _conversation(db, user, request.conversation_id)
    conversation_id = conversation.id
    _save_message(db, conversation, "user", request.message)
    routed = _demand_count_action(db, request.message)
    if routed is None and _field_request(request.message):
        routed = _field_report_for_request(db, conversation, request)
    if routed is None:
        routed = _route_message(db, request, user, conversation)
    if routed is not None:
        done = _finish(db, conversation, *routed)
        return StreamingResponse(iter([_sse("done", done)]), media_type="text/event-stream")
    db.commit()
    messages = _generic_messages(db, request, conversation)

    def events():
        parts: List[str] = []
        failed = False
        try:
            for piece in chat_completion_stream(messages, temperature=0.1, max_tokens=700, enable_thinking=False):
                parts.append(piece)
                yield _sse("token", {"text": piece})
        except Exception as exc:
            failed = True
            logger.warning("Assistant streaming failed: %s", exc)
        reply = "".join(parts).strip()
        if not reply:
            reply = _FALLBACK_REPLY
        elif failed:
            yield _sse("error", {"detail": "The answer was interrupted."})
        # The request session is closed once the response starts, so save with a fresh one.
        with SessionLocal() as save_db:
            conv = save_db.get(Conversation, conversation_id)
            yield _sse("done", _finish(save_db, conv, reply, {"action": "reply"}))

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
    text = None
    if kind == "auto":
        # No choice needed from the user: read the document and decide from its content.
        kind = "resume"
        if is_supported_jd_file(filename):
            try:
                text = extract_text_from_file(filename, content).strip()
                kind = detect_document_kind(filename, text)
            except Exception as exc:
                logger.info("Document type detection fell back to resume for %s: %s", filename, exc)
    if kind == "jd":
        if not is_supported_jd_file(filename):
            raise HTTPException(400, "Unsupported demand document type.")
        text = text if text is not None else extract_text_from_file(filename, content).strip()
        if not text:
            raise HTTPException(400, "No readable text found in the uploaded demand document.")
        file_url, _ = save_upload_file(filename, content, category="job_descriptions")
        title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:200] or "Uploaded Job Description"
        session, messages = assistant_demand.begin(db, user, conversation, title=title, text=text, filename=filename, file_url=file_url, persist=False)
        data = {"action": "demand_session", "reply": "\n\n".join(m["content"] for m in messages), "session": assistant_demand.view(db, session)}
        _save_message(db, conversation, "assistant", data["reply"], {"action": "demand_session"})
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
