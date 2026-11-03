"""Guided demand creation in the chat assistant.

The server owns the workflow: which field is current, what has been collected, what is valid. Values are normalised
and validated by backend/services/common/demand_fields.py (the New Demand form's fields and the demand API's own
schema) and the demand is created through the existing `create_jd`. The language model is only used, through the
existing document pipeline, to read a JD; it never chooses the next field and its output is validated like user input.

Sessions belong to one user and one conversation. TruHire has no organisation/tenant model, so the user is the
isolation boundary: every operation loads the session with `user_id == current user` and answers 404 otherwise.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import DEMAND_SESSION_ACTIVE, AssistantDemandSession, Conversation, ConversationMessage, User, canonical_demand_id
from backend.routers.job_descriptions import create_jd
from backend.services.classification import classify_jd_detailed
from backend.services.common import ai_audit
from backend.services.common import demand_fields as df
from backend.services.ingestion.parsing import extract_text_from_file, is_supported_jd_file
from backend.services.ingestion.storage import save_upload_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant/demand-sessions", tags=["assistant-demand"])

CREATE_INTENT = re.compile(
    r"\b(create|add|raise|start|make|open|set\s*up|build)\b[^.?!\n]{0,30}\b(demands?|requirements?|jds?|job\s+descriptions?)\b", re.I)
STALE_CREATING = timedelta(minutes=2)
MODES = ("all_fields", "step_by_step")


def wants_new_demand(message: str) -> bool:
    """A short message asking to create a demand (a long pasted JD is handled by the caller)."""
    text = (message or "").strip()
    return len(text) <= 180 and bool(CREATE_INTENT.search(text)) and not text.endswith("?")


# ---------------------------------------------------------------- persistence helpers

def _emit(db: Session, conversation: Conversation, role: str, content: str, persist: bool, data: Optional[dict] = None) -> dict:
    if persist:
        db.add(ConversationMessage(conversation_id=conversation.id, role=role, content=content[:20000], message_data=data or {}))
        conversation.updated_at = datetime.utcnow()
    return {"role": role, "content": content, "data": data or {}}


def _audit(event: str, session: AssistantDemandSession, **details: Any) -> None:
    ai_audit.record(provider="assistant", status="ok", feature="demand_session",
                    details={"event": event, "session_id": session.id, "user_id": session.user_id, **details})


def _owned(db: Session, user: User, session_id: str, lock: bool = False) -> AssistantDemandSession:
    query = db.query(AssistantDemandSession).filter(AssistantDemandSession.id == session_id, AssistantDemandSession.user_id == user.id)
    found = (query.with_for_update() if lock else query).first()
    if not found:
        raise HTTPException(404, "Demand session not found.")
    return found


def active_session(db: Session, user: User, conversation_id: Optional[str]) -> Optional[AssistantDemandSession]:
    if not conversation_id:
        return None
    return db.query(AssistantDemandSession).filter(
        AssistantDemandSession.conversation_id == conversation_id, AssistantDemandSession.user_id == user.id,
        AssistantDemandSession.status.in_(DEMAND_SESSION_ACTIVE),
    ).order_by(AssistantDemandSession.created_at.desc()).first()


# ---------------------------------------------------------------- state helpers

def _set(s: AssistantDemandSession, key: str, value: Any, source: str) -> None:
    s.values = {**(s.values or {}), key: value}
    previous = (s.sources or {}).get(key)
    s.sources = {**(s.sources or {}), key: "document" if previous == "document" and source == "user" else source}
    s.errors = {k: v for k, v in (s.errors or {}).items() if k != key}


def _unsettled(s: AssistantDemandSession) -> List[str]:
    return [k for k in df.KEYS if k not in (s.sources or {})]


def _missing_required(s: AssistantDemandSession) -> List[str]:
    values = s.values or {}
    return [k for k in df.REQUIRED_KEYS if values.get(k) in (None, "")]


def _advance(s: AssistantDemandSession) -> None:
    """Step-by-step: the next field is the first one in form order that has no answer yet; none left = review."""
    pending = _unsettled(s)
    if pending:
        s.status, s.current_field = "collecting", pending[0]
    elif _missing_required(s):
        s.status, s.current_field = "collecting", _missing_required(s)[0]
    else:
        s.status, s.current_field = "review", None


def _label(key: str) -> str:
    return df.BY_KEY[key]["label"]


def _show(db: Session, s: AssistantDemandSession, key: str) -> str:
    return df.display(key, (s.values or {}).get(key), db)


def _next_question(s: AssistantDemandSession) -> str:
    field = df.BY_KEY[s.current_field]
    hint = "" if field["required"] else " You can skip this one."
    return f"{field['prompt']}{hint}"


def _step_progress(s: AssistantDemandSession) -> Dict[str, int]:
    """Step n of N counts the fields the user is asked for; those read from a document are not asked."""
    sources = s.sources or {}
    total = sum(1 for k in df.KEYS if sources.get(k) != "document")
    done = sum(1 for k in df.KEYS if sources.get(k) in ("user", "skipped"))
    return {"step": min(done + 1, total), "total": total}


def view(db: Session, s: AssistantDemandSession) -> dict:
    values = s.values or {}
    fields = []
    for definition in df.field_definitions(db):
        key = definition["key"]
        fields.append({**definition, "value": values.get(key), "text": df.display(key, values.get(key), db),
                       "source": (s.sources or {}).get(key), "error": (s.errors or {}).get(key)})
    out = {
        "id": s.id, "conversation_id": s.conversation_id, "status": s.status, "input_mode": s.input_mode,
        "current_field": s.current_field, "fields": fields, "missing_required": [_label(k) for k in _missing_required(s)],
        "source_document": s.source_document,
    }
    if s.input_mode == "step_by_step" and s.status == "collecting":
        out["progress"] = _step_progress(s)
        out["question"] = _next_question(s) if s.current_field else None
    return out


# ---------------------------------------------------------------- document / pasted-text extraction

def apply_extraction(db: Session, s: AssistantDemandSession, title: str, text: str, filename: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """Prefill from a JD. Only values the existing JD reader found are used, each validated like a typed answer.
    Returns (labels filled, notes about values that were unclear or failed validation)."""
    from backend.routers.assistant import _jd_field_report  # deferred: assistant.py imports this module

    notes: List[str] = []
    found: Dict[str, Any] = {"jd_text": text, "title": title}
    try:
        values = _jd_field_report(title, text)["values"]
        found.update({
            "title": values.get("title") or title, "client_name": values.get("client_name"),
            "experience_years": values.get("experience_years"), "experience_max_years": values.get("experience_max_years"),
            "locations": values.get("locations") or None, "no_of_positions": values.get("position_count"),
            "start_date": values.get("start_date"), "end_date": values.get("end_date"),
        })
    except Exception as exc:  # the reader may call the model; the form can still be filled by hand
        logger.warning("Demand details could not be read from the document: %s", exc)
        notes.append("I couldn't read the details automatically, so I'll ask for them.")
    try:
        classification = classify_jd_detailed(title, text)
        if classification.confident:
            found["demand_id"] = canonical_demand_id(classification.category)
        else:
            notes.append("I couldn't tell which Demand Practice this belongs to.")
    except Exception as exc:
        logger.warning("Practice classification failed: %s", exc)

    filled: List[str] = []
    for key in df.KEYS:
        if (s.sources or {}).get(key) in ("user", "skipped") or found.get(key) in (None, "", []):
            continue
        value, error = df.normalize(key, found[key], db)
        if error or value is None:
            notes.append(f"{_label(key)}: {error or 'unclear'}")
            continue
        trial = {**(s.values or {}), key: value}
        if df.cross_check(trial):
            notes.append(f"{_label(key)}: the value in the document conflicts with another detail.")
            continue
        _set(s, key, value, "document")
        filled.append(_label(key))
    return filled, notes


def _document_summary(s: AssistantDemandSession, filled: List[str], notes: List[str], filename: Optional[str]) -> str:
    source = f"“{filename}”" if filename else "the text you sent"
    lines = [f"I read {source}." + (f" I filled in: {', '.join(filled)}." if filled else " I couldn't confidently fill in any fields.")]
    still = [_label(k) for k in _unsettled(s)]
    if still:
        lines.append(f"Still to provide: {', '.join(still)}.")
    if notes:
        lines.append("Needs your attention: " + "; ".join(notes))
    return " ".join(lines)


# ---------------------------------------------------------------- starting

def begin(db: Session, user: User, conversation: Conversation, *, title: Optional[str] = None, text: Optional[str] = None,
          filename: Optional[str] = None, file_url: Optional[str] = None, persist: bool = True) -> Tuple[AssistantDemandSession, List[dict]]:
    """Start (or continue) the guided workflow. One active session per conversation; a second request continues it."""
    existing = active_session(db, user, conversation.id)
    if existing and not text:
        msg = _emit(db, conversation, "assistant", "You already have a demand in progress. Let's continue with it, or cancel it to start over.", persist)
        return existing, [msg]
    if existing:
        existing.status = "cancelled"
        _audit("superseded", existing)
    s = AssistantDemandSession(conversation_id=conversation.id, user_id=user.id, status="choose_mode", values={}, sources={}, errors={})
    db.add(s)
    db.flush()
    messages: List[dict] = []
    if text:
        guessed = title or next((line.strip() for line in text.splitlines() if line.strip()), "Uploaded Job Description")[:200]
        s.source_document = {"filename": filename, "file_url": file_url}
        filled, notes = apply_extraction(db, s, guessed, text, filename)
        messages.append(_emit(db, conversation, "assistant", _document_summary(s, filled, notes, filename), persist))
    messages.append(_emit(db, conversation, "assistant", "How would you like to fill in the demand details?", persist))
    _audit("started", s, with_document=bool(text))
    return s, messages


# ---------------------------------------------------------------- request models

class StartRequest(BaseModel):
    conversation_id: Optional[str] = None


class ModeRequest(BaseModel):
    mode: str


class AnswerRequest(BaseModel):
    field: Optional[str] = None  # defaults to the current field
    value: Any = None


class AnswersRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class FieldRequest(BaseModel):
    field: str


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)


def _respond(db: Session, s: AssistantDemandSession, messages: List[dict], **extra: Any) -> dict:
    s.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    return {"session": view(db, s), "messages": messages, **extra}


def _conversation_for(db: Session, user: User, conversation_id: Optional[str]) -> Conversation:
    found = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first() if conversation_id else None
    if conversation_id and not found:
        raise HTTPException(404, "Conversation not found.")
    if not found:
        found = Conversation(user_id=user.id, title="TruHire Assistant")
        db.add(found)
        db.flush()
    return found


def _open(db: Session, user: User, session_id: str, lock: bool = False) -> Tuple[AssistantDemandSession, Conversation]:
    s = _owned(db, user, session_id, lock)
    if s.status in ("created", "cancelled"):
        raise HTTPException(409, "This demand session is already finished.")
    if s.status == "creating" and datetime.utcnow() - (s.updated_at or datetime.utcnow()) < STALE_CREATING:
        raise HTTPException(409, "This demand is being created. Please wait a moment.")
    return s, s.conversation


# ---------------------------------------------------------------- endpoints

@router.get("/fields")
def get_fields(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"fields": df.field_definitions(db)}


@router.post("")
def start(request: StartRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = _conversation_for(db, user, request.conversation_id)
    s, messages = begin(db, user, conversation)
    return _respond(db, s, messages, conversation_id=conversation.id)


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"session": view(db, _owned(db, user, session_id))}


@router.post("/{session_id}/document")
async def attach_document(session_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s, conversation = _open(db, user, session_id)
    filename = file.filename or "uploaded-document"
    if not is_supported_jd_file(filename):
        raise HTTPException(400, "Unsupported demand document type.")
    content = await file.read()
    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        text = extract_text_from_file(filename, content).strip()
    except Exception as exc:
        logger.info("Demand document could not be parsed (%s): %s", filename, exc)
        text = ""
    if not text:
        msg = _emit(db, conversation, "assistant", f"I couldn't read any text from “{filename}”. You can try another file or fill in the details yourself.", True)
        return _respond(db, s, [msg])
    file_url, _ = save_upload_file(filename, content, category="job_descriptions")
    title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()[:200] or "Uploaded Job Description"
    s.source_document = {"filename": filename, "file_url": file_url}
    filled, notes = apply_extraction(db, s, title, text, filename)
    messages = [_emit(db, conversation, "assistant", _document_summary(s, filled, notes, filename), True)]
    if s.input_mode == "step_by_step":
        _advance(s)
        messages.append(_emit(db, conversation, "assistant", _next_question(s) if s.current_field else "All required demand details have been collected. Please review your demand before creating it.", True))
    elif s.status == "review":
        s.status = "collecting"
    _audit("document", s, filename=filename, filled=filled)
    return _respond(db, s, messages)


def _enter_mode(db: Session, s: AssistantDemandSession, conversation: Conversation, mode: str) -> List[dict]:
    s.input_mode = mode
    s.errors = {}
    if mode == "all_fields":
        s.status, s.current_field = "collecting", None
        return [_emit(db, conversation, "assistant", "Here is the full demand form. Review the values, fill in the rest, then continue.", True)]
    _advance(s)
    intro = _emit(db, conversation, "assistant", "Let's create your demand step by step.", True)
    if s.status == "review":
        return [intro, _emit(db, conversation, "assistant", "All required demand details have been collected. Please review your demand before creating it.", True)]
    return [intro, _emit(db, conversation, "assistant", _next_question(s), True)]


@router.post("/{session_id}/mode")
def set_mode(session_id: str, request: ModeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if request.mode not in MODES:
        raise HTTPException(422, "Choose all_fields or step_by_step.")
    s, conversation = _open(db, user, session_id)
    label = "Fill all fields at once" if request.mode == "all_fields" else "Fill one by one"
    messages = [_emit(db, conversation, "user", label, True)] + _enter_mode(db, s, conversation, request.mode)
    _audit("mode", s, mode=request.mode)
    return _respond(db, s, messages)


def _answer(db: Session, s: AssistantDemandSession, conversation: Conversation, key: str, raw: Any, echo: bool = True) -> List[dict]:
    """One field answer in step-by-step mode (or a single edit). Invalid answers keep the same field open."""
    field = df.BY_KEY[key]
    messages: List[dict] = []
    if echo:
        shown = ", ".join(raw) if isinstance(raw, list) else str(raw)
        messages.append(_emit(db, conversation, "user", shown[:500], True))
    value, error = df.normalize(key, raw, db)
    if not error:
        conflicts = df.cross_check({**(s.values or {}), key: value})
        if conflicts:
            error = next(iter(conflicts.values()))
    if error:
        s.errors = {**(s.errors or {}), key: error}
        s.current_field = key
        s.status = "collecting"
        messages.append(_emit(db, conversation, "assistant", f"{error} Please try again.\n\n{_next_question(s) if s.input_mode == 'step_by_step' else field['prompt']}", True))
        return messages
    left_blank = value is None
    if left_blank and "default" in field:
        value = field["default"]  # the form's own default (No. of Positions starts at 1)
    _set(s, key, value, "skipped" if left_blank else "user")
    ack = f"Got it. {field['label']}: {df.display(key, value, db)}." if value is not None else f"Okay, I'll leave {field['label']} blank."
    if s.input_mode == "step_by_step" or s.status == "review":
        was_review = s.status == "review"
        _advance(s)
        if s.status == "review":
            messages.append(_emit(db, conversation, "assistant", ack + "\n\nAll required demand details have been collected. Please review your demand before creating it." if not was_review else ack + " Review the updated details below.", True))
        else:
            messages.append(_emit(db, conversation, "assistant", f"{ack}\n\nNext: {_next_question(s)}", True))
    else:
        messages.append(_emit(db, conversation, "assistant", ack, True))
    return messages


@router.post("/{session_id}/answer")
def answer(session_id: str, request: AnswerRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s, conversation = _open(db, user, session_id)
    if s.status in ("choose_mode",):
        raise HTTPException(409, "Choose how you want to fill in the details first.")
    key = request.field or s.current_field
    if key not in df.BY_KEY:
        raise HTTPException(422, "Unknown field.")
    if s.input_mode == "step_by_step" and s.status == "collecting" and key != s.current_field and (s.sources or {}).get(key) is None:
        raise HTTPException(409, f"Please answer {_label(s.current_field)} first.")  # fields come one at a time, in form order
    messages = _answer(db, s, conversation, key, request.value)
    return _respond(db, s, messages)


@router.post("/{session_id}/answers")
def submit_all(session_id: str, request: AnswersRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """All-fields mode: every submitted value is validated; valid ones are kept even when others fail."""
    s, conversation = _open(db, user, session_id)
    if s.input_mode != "all_fields":
        raise HTTPException(409, "The all-fields form is not active.")
    errors: Dict[str, str] = {}
    accepted: Dict[str, Any] = {}
    for key in df.KEYS:
        if key not in request.values:
            continue
        value, error = df.normalize(key, request.values[key], db)
        if error:
            errors[key] = error
        else:
            accepted[key] = value
    merged = {**(s.values or {}), **accepted}
    for key, message in df.cross_check({k: v for k, v in merged.items() if k not in errors}).items():
        errors.setdefault(key, message)
        accepted.pop(key, None)
    for key, value in accepted.items():
        if key in errors:
            continue
        _set(s, key, value, "user" if value is not None else "skipped")
    s.errors = errors
    for key in df.REQUIRED_KEYS:
        if (s.values or {}).get(key) in (None, "") and key not in errors:
            s.errors = {**s.errors, key: f"{_label(key)} is required."}
    if s.errors:
        count = len(s.errors)
        messages = [_emit(db, conversation, "assistant", f"{count} field{'s need' if count != 1 else ' needs'} attention: {', '.join(_label(k) for k in s.errors)}. Your other answers are saved.", True)]
        s.status = "collecting"
    else:
        s.status, s.current_field = "review", None
        messages = [_emit(db, conversation, "assistant", "All required demand details have been collected. Please review your demand before creating it.", True)]
    return _respond(db, s, messages)


@router.post("/{session_id}/skip")
def skip(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s, conversation = _open(db, user, session_id)
    key = s.current_field
    if s.input_mode != "step_by_step" or not key:
        raise HTTPException(409, "There is no field to skip.")
    if df.BY_KEY[key]["required"]:
        raise HTTPException(422, f"{_label(key)} is required and can't be skipped.")
    return _respond(db, s, _answer(db, s, conversation, key, None, echo=False))


@router.post("/{session_id}/back")
def back(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s, conversation = _open(db, user, session_id)
    if s.input_mode != "step_by_step":
        raise HTTPException(409, "Going back applies to step-by-step mode.")
    order = df.KEYS
    limit = order.index(s.current_field) if s.current_field else len(order)
    previous = next((k for k in reversed(order[:limit]) if (s.sources or {}).get(k) in ("user", "skipped")), None)
    if not previous:
        raise HTTPException(409, "There is no earlier answer to go back to.")
    s.status, s.current_field, s.errors = "collecting", previous, {}
    messages = [_emit(db, conversation, "assistant", f"Going back to {_label(previous)} (currently {_show(db, s, previous)}).\n\n{_next_question(s)}", True)]
    return _respond(db, s, messages)


@router.post("/{session_id}/edit")
def edit(session_id: str, request: FieldRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Edit one completed answer without restarting. In review it returns to review afterwards."""
    s, conversation = _open(db, user, session_id)
    if request.field not in df.BY_KEY:
        raise HTTPException(422, "Unknown field.")
    if s.input_mode == "all_fields":
        s.status, s.current_field = "collecting", None
        messages = [_emit(db, conversation, "assistant", f"You can change {_label(request.field)} in the form.", True)]
        return _respond(db, s, messages)
    s.status, s.current_field, s.errors = "collecting", request.field, {}
    messages = [_emit(db, conversation, "assistant", f"{_label(request.field)} is currently {_show(db, s, request.field)}.\n\n{df.BY_KEY[request.field]['prompt']}", True)]
    return _respond(db, s, messages)


COMMANDS = {
    "cancel": re.compile(r"^(cancel|stop|abort|never\s*mind|discard)( this| the)?( demand)?\W*$", re.I),
    "back": re.compile(r"^(back|go back|previous|undo)\W*$", re.I),
    "skip": re.compile(r"^skip\W*$", re.I),
    "all_fields": re.compile(r"^(fill )?all( fields)?( at once)?\W*$|^(use|switch to) (the )?(form|all fields)\W*$", re.I),
    "step_by_step": re.compile(r"^(fill )?(one by one|step by step)\W*$|^(switch to) (one by one|step[- ]by[- ]step)\W*$", re.I),
    "confirm": re.compile(r"^(confirm|create( it| demand| the demand)?|yes,? create( it)?)\W*$", re.I),
}
EDIT_COMMAND = re.compile(r"^(?:edit|change|update)\s+(?:the\s+)?(.+?)\W*$", re.I)


def _field_from_words(words: str) -> Optional[str]:
    words = words.strip().lower()
    aliases = {"practice": "demand_id", "demand practice": "demand_id", "client": "client_name", "min experience": "experience_years",
               "minimum experience": "experience_years", "max experience": "experience_max_years", "maximum experience": "experience_max_years",
               "location": "locations", "positions": "no_of_positions", "start": "start_date", "end": "end_date", "end date": "end_date",
               "spec": "jd_text", "description": "jd_text", "jd": "jd_text"}
    if words in aliases:
        return aliases[words]
    return next((f["key"] for f in df.FIELDS if f["label"].lower() == words or f["label"].lower().startswith(words) and len(words) >= 4), None)


@router.post("/{session_id}/message")
def message(session_id: str, request: MessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Typed chat text while a session is open: a command (cancel, back, skip, edit <field>, switch mode, confirm) or the
    answer to the current field. Anything that cannot be an answer is explained, never guessed."""
    s, conversation = _open(db, user, session_id)
    text = request.text.strip()
    for name, pattern in COMMANDS.items():
        if pattern.match(text):
            if name == "cancel":
                return cancel(session_id, db, user)
            if name == "back":
                return back(session_id, db, user)
            if name == "skip" and s.input_mode == "step_by_step" and s.current_field:
                return skip(session_id, db, user)
            if name in MODES:
                return set_mode(session_id, ModeRequest(mode=name), db, user)
            if name == "confirm" and s.status == "review":
                return confirm(session_id, db, user)
    user_msg = _emit(db, conversation, "user", text[:500], True)
    wanted = EDIT_COMMAND.match(text)
    if wanted and _field_from_words(wanted.group(1)) and s.status in ("review", "collecting") and s.input_mode:
        result = edit(session_id, FieldRequest(field=_field_from_words(wanted.group(1))), db, user)
        result["messages"].insert(0, user_msg)
        return result
    if s.status == "choose_mode" or s.input_mode == "all_fields" or s.status == "review" or not s.current_field:
        hint = {"choose_mode": "Please choose “Fill all fields at once” or “Fill one by one”.",
                "review": "Use “Confirm and Create Demand” or “Edit Details”, or say which field to change.",
                }.get(s.status, "Use the form to fill in the details, or say “one by one” to switch.")
        return _respond(db, s, [user_msg, _emit(db, conversation, "assistant", hint, True)])
    return _respond(db, s, [user_msg] + _answer(db, s, conversation, s.current_field, text, echo=False))


@router.post("/{session_id}/cancel")
def cancel(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s, conversation = _open(db, user, session_id)
    s.status, s.current_field = "cancelled", None
    messages = [_emit(db, conversation, "assistant", "Demand creation cancelled. Nothing was created.", True)]
    _audit("cancelled", s)
    return _respond(db, s, messages)


@router.post("/{session_id}/confirm")
def confirm(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create the demand through the existing demand API logic. Safe to call twice: the second call returns the first result."""
    s = _owned(db, user, session_id, lock=True)
    if s.status == "created":
        return _respond(db, s, [], created=_created(db, s))
    if s.status == "creating" and datetime.utcnow() - (s.updated_at or datetime.utcnow()) < STALE_CREATING:
        raise HTTPException(409, "This demand is already being created.")
    if s.status == "cancelled":
        raise HTTPException(409, "This demand session was cancelled.")
    if s.status not in ("review", "creating"):
        raise HTTPException(409, "Finish the required fields before creating the demand.")
    missing = _missing_required(s)
    if missing:
        raise HTTPException(422, "Missing required fields: " + ", ".join(_label(k) for k in missing))
    try:
        request = df.build_request({**(s.values or {}), "file_url": (s.source_document or {}).get("file_url"),
                                    "original_filename": (s.source_document or {}).get("filename")})
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))
    s.status = "creating"
    db.commit()
    try:
        created = create_jd(request, db, user, source="assistant")
    except HTTPException as exc:
        db.rollback()
        s = _owned(db, user, session_id, lock=True)
        s.status = "review"
        db.commit()
        _audit("create_failed", s, detail=str(exc.detail))
        raise
    except Exception:
        db.rollback()
        s = _owned(db, user, session_id, lock=True)
        s.status = "review"
        db.commit()
        logger.exception("Assistant demand creation failed")
        raise HTTPException(500, "The demand could not be created. Your answers are saved; please try again.")
    s = _owned(db, user, session_id, lock=True)
    s.status, s.current_field, s.created_position_id = "created", None, created.id
    summary = f"Your demand has been created successfully. {created.display_id} · {created.title}"
    position = {"id": created.id, "display_id": created.display_id, "title": created.title}
    messages = [_emit(db, s.conversation, "assistant", summary, True, {"action": "created", "position": position})]
    _audit("created", s, position_id=created.id)
    return _respond(db, s, messages, created=position)


def _created(db: Session, s: AssistantDemandSession) -> dict:
    from backend.models import Position
    p = db.query(Position).filter(Position.id == s.created_position_id).first()
    return {"id": p.id, "display_id": p.display_id, "title": p.title} if p else {"id": s.created_position_id}
