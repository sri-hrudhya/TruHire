"""The TruHire assistant as a tool-calling agent.

The model decides which tool to call; every tool reuses the code the REST endpoints already use.
  * READ tools run immediately and feed their result back to the model (wrapped as untrusted data).
  * WRITE tools never run here: they only create a *pending action* that the user must confirm in the chat
    (POST /api/assistant/confirm). Starting a guided demand session and opening an email draft are not data
    changes, so they run directly.
Memory without a new table: a per-user conversation titled MEMORY_TITLE holds one ``memory`` message whose
message_data keeps short notes the user asked to remember and the candidate/demand last talked about.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.models import (INACTIVE_JD_STATUSES, LEGACY_JD_STATUS_ALIASES, REQUIREMENT_STATUSES, Candidate,
                            CandidateActivity, Conversation, ConversationMessage, Position, User)
from backend.services.candidates.directory import filter_directory
from backend.services.candidates.history import requirement_rows
from backend.services.common import ai_audit
from backend.services.common.payloads import candidate_payload
from backend.services.llm.ai_service import untrusted
from backend.services.llm.assistant_prompt import build_agent_prompt
from backend.services.llm.router import chat_with_tools
from backend.services.retrieval.client_search import search_client_requirements
from backend.services.retrieval.search import execute_candidate_search

logger = logging.getLogger(__name__)

MEMORY_TITLE = "__truhire_memory__"
MAX_ROUNDS = 5
HISTORY_TURNS = 12
MAX_RESULT_CHARS = 6000
PENDING_TTL = timedelta(hours=1)
AVAILABILITY = ("Active", "Not Active")


class AgentUnavailable(Exception):
    """No model could take a tool-calling turn; the caller falls back to the deterministic handlers."""


@dataclass
class Outcome:
    result: Dict[str, Any]
    ui: Optional[dict] = None          # payload shape the chat UI already renders
    pending: Optional[dict] = None     # a write waiting for the user's confirmation
    final: Optional[str] = None        # when set, the turn ends with this reply (no further model call)


# ----------------------------------------------------------------------------- lookups

def _find_candidates(db: Session, ref: Optional[str], limit: int = 5) -> List[Candidate]:
    ref = (ref or "").strip()
    display_id = re.search(r"\bTRU-CN-\d+\b", ref, re.I)
    if display_id:
        return db.query(Candidate).filter(Candidate.display_id.ilike(display_id.group(0))).all()
    if len(ref) < 2:
        return []
    return filter_directory(db.query(Candidate), ref).limit(limit).all()


def _one_candidate(db: Session, ref: Optional[str]) -> Tuple[Optional[Candidate], Optional[Outcome]]:
    found = _find_candidates(db, ref)
    exact = [c for c in found if (c.candidate_name or "").casefold() == (ref or "").strip().casefold()]
    if len(exact) == 1:
        return exact[0], None
    if not found:
        return None, Outcome({"error": f"No candidate matches '{ref}'. Ask for a name, email, phone, company or TRU-CN id."})
    if len(found) > 1:
        return None, Outcome({"error": "More than one candidate fits; ask the user which one.",
                              "candidates": [_candidate_brief(c) for c in found]},
                             ui={"action": "candidate_lookup", "query": ref, "results": [candidate_payload(c) for c in found]})
    return found[0], None


def _find_demands(db: Session, ref: Optional[str], limit: int = 5) -> List[Position]:
    ref = (ref or "").strip()
    query = db.query(Position).options(joinedload(Position.demand))
    number = re.search(r"\bDM-(\d+)\b", ref, re.I)
    if number:
        return query.filter(Position.display_id.ilike(f"DM-{int(number.group(1)):04d}")).all()
    terms = [t for t in re.findall(r"[a-z0-9]+", ref.lower()) if len(t) > 1]
    if not terms:
        return []
    rows = []
    for p in query.order_by(Position.created_at.desc()).all():
        indexed = " ".join((p.title or "", p.role or "", p.client_name or "", p.demand.name if p.demand else "")).lower()
        if all(t in indexed for t in terms):
            rows.append(p)
    return rows[:limit]


def _one_demand(db: Session, ref: Optional[str]) -> Tuple[Optional[Position], Optional[Outcome]]:
    found = _find_demands(db, ref)
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, Outcome({"error": f"No demand matches '{ref}'. Ask for the demand ID (DM-0001) or its title and client."})
    return None, Outcome({"error": "More than one demand fits; ask the user which one.", "demands": [_demand_row(p) for p in found]})


def _status(p: Position) -> str:
    raw = p.status or "Open"
    return LEGACY_JD_STATUS_ALIASES.get(raw, raw)


def _demand_row(p: Position) -> dict:
    row = {"id": p.id, "display_id": p.display_id, "title": p.title, "client_name": p.client_name,
           "practice": p.demand.name if p.demand else None, "status": _status(p), "no_of_positions": p.no_of_positions,
           "locations": p.locations or ([p.location] if p.location else None), "experience_years": p.experience_years,
           "experience_max_years": p.experience_max_years, "start_date": p.start_date, "end_date": p.end_date,
           "demand_owner": p.demand_owner}
    return {k: v for k, v in row.items() if v not in (None, "", [])}


def _candidate_brief(c: Candidate) -> dict:
    return {"id": c.id, "display_id": c.display_id, "name": c.candidate_name, "current_company": c.current_company,
            "email": c.email, "phone": c.phone, "years_experience": c.years_experience,
            "availability": c.availability_status or "Active"}


def _demand_label(p: Position) -> str:
    return f"{p.display_id or 'JD'} · {p.title}" + (f" ({p.client_name})" if p.client_name else "")


# ----------------------------------------------------------------------------- shared builders

def history_data(db: Session, candidate: Candidate) -> Tuple[str, dict]:
    """Where a candidate was submitted (client - status) plus the recorded notes, newest first."""
    submitted = requirement_rows(db, [candidate.id])[candidate.id]
    events = (db.query(CandidateActivity).filter(CandidateActivity.candidate_id == candidate.id)
              .order_by(CandidateActivity.occurred_at.desc(), CandidateActivity.id.desc()).limit(10).all())
    who = f"{candidate.candidate_name} ({candidate.display_id})" if candidate.display_id else candidate.candidate_name
    line = ", ".join(f"{item['client_name'] or item['title']} - {item['status']}" for item in submitted)
    reply = (f"{who} is {candidate.availability_status or 'Active'}. " +
             (f"Submitted to: {line}." if submitted else "Not submitted to any requirement yet.") +
             ("" if events else " No notes are recorded yet."))
    return reply, {"action": "candidate_history", "candidate_id": candidate.id,
                   "candidate_display_id": candidate.display_id, "candidate_name": candidate.candidate_name,
                   "availability_status": candidate.availability_status or "Active", "requirements": submitted,
                   "items": [{"event_type": row.event_type, "timestamp": row.occurred_at.isoformat(), "actor": row.actor_name,
                              "summary": row.summary, "client_name": row.client_name,
                              "position_title": row.position_title} for row in events]}


# ----------------------------------------------------------------------------- memory

def _memory_row(db: Session, user: User, create: bool = False) -> Optional[ConversationMessage]:
    conv = db.query(Conversation).filter(Conversation.user_id == user.id, Conversation.title == MEMORY_TITLE).first()
    if conv is None:
        if not create:
            return None
        conv = Conversation(user_id=user.id, title=MEMORY_TITLE)
        db.add(conv)
        db.flush()
    row = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conv.id, ConversationMessage.role == "memory").first()
    if row is None and create:
        row = ConversationMessage(conversation_id=conv.id, role="memory", content="memory", message_data={"notes": [], "recent": {}})
        db.add(row)
        db.flush()
    return row


def load_memory(db: Session, user: User) -> dict:
    row = _memory_row(db, user)
    return dict(row.message_data or {}) if row else {}


def _update_memory(db: Session, user: User, *, note: Optional[str] = None, recent: Optional[dict] = None) -> None:
    row = _memory_row(db, user, create=True)
    data = dict(row.message_data or {})
    notes = list(data.get("notes") or [])
    if note:
        clean = " ".join(note.split())[:200]
        if clean and clean not in notes:
            notes.append(clean)
    data["notes"] = notes[-10:]
    if recent:
        data["recent"] = {**(data.get("recent") or {}), **recent}
    row.message_data = data  # reassign: JSON columns do not track in-place edits


# ----------------------------------------------------------------------------- tool schemas

def _tool(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []}}}


_STR = {"type": "string"}
TOOLS: List[dict] = [
    _tool("search_candidates", "Find candidates by name, email, phone number, current company or TRU-CN id. Returns near matches.",
          {"query": _STR, "limit": {"type": "integer"}}, ["query"]),
    _tool("get_candidate_history", "Where a candidate was submitted (client - status), their availability and the recorded notes.",
          {"candidate": {**_STR, "description": "name, email, phone, company or TRU-CN id"}}, ["candidate"]),
    _tool("compare_candidates", "Side-by-side profile of 2 or 3 candidates.", {"candidates": {"type": "array", "items": _STR}}, ["candidates"]),
    _tool("list_demands", "List saved demands/requirements, optionally filtered by client, practice or status (Open, Mapped, Fulfilled, Cancelled). "
          "Includes the number of open positions.", {"client": _STR, "practice": _STR, "status": _STR, "limit": {"type": "integer"}}),
    _tool("get_demand", "Details of one demand, including no_of_positions (open positions). Use the DM-0001 id or title words.",
          {"demand": {**_STR, "description": "DM- id, or title/client words"}}, ["demand"]),
    _tool("match_candidates", "Best matching candidates for one demand with match score, matched skills and missing skills.",
          {"demand": _STR, "top_n": {"type": "integer"}}, ["demand"]),
    _tool("search_client_requirements", "Best candidates for every active demand of a client, grouped by demand.",
          {"client": _STR, "top_n": {"type": "integer"}}, ["client"]),
    _tool("remember", "Save a short note about the user's preference or working context so it is available in later chats.",
          {"note": _STR}, ["note"]),
    _tool("update_requirement_status", "PROPOSE changing a candidate's status for one demand. The user must confirm before it happens. "
          f"Statuses: {', '.join(REQUIREMENT_STATUSES)}.", {"candidate": _STR, "demand": _STR, "status": {"type": "string", "enum": list(REQUIREMENT_STATUSES)}},
          ["candidate", "demand", "status"]),
    _tool("set_availability", "PROPOSE marking a candidate Active or Not Active. The user must confirm before it happens.",
          {"candidate": _STR, "availability": {"type": "string", "enum": list(AVAILABILITY)}}, ["candidate", "availability"]),
    _tool("create_demand", "Start the guided demand-creation form. Pass `details` only when the user pasted a job description.",
          {"details": _STR}),
    _tool("draft_email", "Open the email drafts screen for one demand. Nothing is sent automatically.", {"demand": _STR}, ["demand"]),
]
WRITE_TOOLS = {"update_requirement_status", "set_availability", "create_demand", "draft_email"}


# ----------------------------------------------------------------------------- tool implementations

def _t_search_candidates(ctx, args) -> Outcome:
    limit = max(1, min(int(args.get("limit") or 10), 20))
    found = _find_candidates(ctx.db, args.get("query"), limit)
    return Outcome({"count": len(found), "candidates": [_candidate_brief(c) for c in found]},
                   ui={"action": "candidate_lookup", "query": args.get("query"), "results": [candidate_payload(c) for c in found]})


def _t_get_candidate_history(ctx, args) -> Outcome:
    cand, problem = _one_candidate(ctx.db, args.get("candidate"))
    if problem:
        return problem
    ctx.recent["candidate"] = f"{cand.display_id} {cand.candidate_name}"
    summary, data = history_data(ctx.db, cand)
    return Outcome({"summary": summary, "submitted_to": data["requirements"], "notes": data["items"]}, ui=data)


def _t_compare_candidates(ctx, args) -> Outcome:
    people = []
    for ref in (args.get("candidates") or [])[:3]:
        cand, problem = _one_candidate(ctx.db, ref)
        if problem:
            return problem
        people.append(cand)
    if len(people) < 2:
        return Outcome({"error": "Give at least two candidates to compare."})
    rows = [{"id": c.id, "display_id": c.display_id, "name": c.candidate_name, "status": c.status,
             "years_experience": c.years_experience, "skills": c.extracted_skills or [], "education": c.education} for c in people]
    return Outcome({"candidates": rows}, ui={"action": "candidate_comparison", "candidates": rows})


def _t_list_demands(ctx, args) -> Outcome:
    limit = max(1, min(int(args.get("limit") or 25), 50))
    rows = ctx.db.query(Position).options(joinedload(Position.demand)).order_by(Position.created_at.desc()).all()
    client, practice, status = (str(args.get(k) or "").strip().casefold() for k in ("client", "practice", "status"))
    picked = [p for p in rows
              if (not client or client in (p.client_name or "").casefold())
              and (not practice or practice in (p.demand.name if p.demand else "").casefold())
              and (not status or status == _status(p).casefold())]
    live = [p for p in picked if _status(p) not in INACTIVE_JD_STATUSES]
    result = {"count": len(picked), "live": len(live), "open_positions_in_live_demands": sum(p.no_of_positions or 0 for p in live),
              "demands": [_demand_row(p) for p in picked[:limit]]}
    ui = None
    if picked:
        brief = [{"id": p.id, "display_id": p.display_id, "title": p.title, "client_name": p.client_name, "demand_id": p.demand_id,
                  "demand_name": p.demand.name if p.demand else None} for p in picked[:limit]]
        grouped: Dict[str, list] = {}
        for item in brief:
            grouped.setdefault((item["client_name"] or "").strip() or "No client assigned", []).append(item)
        ui = ({"action": "client_demands", "client_name": picked[0].client_name, "requirements": brief} if client
              else {"action": "client_groups", "clients": [{"name": n, "count": len(v), "requirements": v} for n, v in sorted(grouped.items())]})
    return Outcome(result, ui=ui)


def _t_get_demand(ctx, args) -> Outcome:
    pos, problem = _one_demand(ctx.db, args.get("demand"))
    if problem:
        return problem
    ctx.recent["demand"] = _demand_label(pos)
    row = {"id": pos.id, "display_id": pos.display_id, "title": pos.title, "client_name": pos.client_name,
           "status": _status(pos), "no_of_positions": pos.no_of_positions}
    return Outcome({**_demand_row(pos), "jd_excerpt": (pos.jd_text or "")[:600]}, ui={"action": "open_positions", "total": pos.no_of_positions or 0, "requirements": [row]})


def _t_match_candidates(ctx, args) -> Outcome:
    pos, problem = _one_demand(ctx.db, args.get("demand"))
    if problem:
        return problem
    ctx.recent["demand"] = _demand_label(pos)
    top_n = max(1, min(int(args.get("top_n") or pos.no_of_positions or 5), 25))
    result = execute_candidate_search(ctx.db, position_id=pos.id, top_n=top_n)
    rows = result.get("results", [])
    brief = [{"candidate_id": r["candidate"]["id"], "display_id": r["candidate"].get("display_id"), "name": r["candidate"].get("candidate_name"),
              "match_score": r.get("match_score"), "matched_skills": (r.get("score_breakdown") or {}).get("matched_skills", [])[:8],
              "missing_skills": (r.get("score_breakdown") or {}).get("missing_skills", [])[:8]} for r in rows]
    return Outcome({"demand": _demand_label(pos), "total_matches": result.get("total_matches", len(rows)), "top": brief},
                   ui={"action": "matches", "position": {"id": pos.id, "display_id": pos.display_id, "title": pos.title, "no_of_positions": top_n},
                       "results": rows, "total_matches": result.get("total_matches", 0)})


def _t_search_client_requirements(ctx, args) -> Outcome:
    client = str(args.get("client") or "").strip()
    result = search_client_requirements(ctx.db, client, "", top_n=max(1, min(int(args.get("top_n") or 5), 10)))
    groups = result.get("client_groups", [])
    brief = [{"demand": f"{g['position'].get('display_id')} · {g['position'].get('title')}",
              "top": [{"name": r["candidate"].get("candidate_name"), "match_score": r.get("match_score")} for r in g.get("results", [])[:5]]} for g in groups]
    return Outcome({"client": client, "total_matches": result.get("total_matches", 0), "groups": brief},
                   ui={"action": "client_candidate_matches", "client_name": client, "client_groups": groups, "total_matches": result.get("total_matches", 0)})


def _t_remember(ctx, args) -> Outcome:
    note = str(args.get("note") or "").strip()
    if not note:
        return Outcome({"error": "Nothing to remember."})
    _update_memory(ctx.db, ctx.user, note=note)
    return Outcome({"saved": True})


def _pending(ctx, tool: str, args: dict, summary: str) -> Outcome:
    pending = {"id": uuid.uuid4().hex, "tool": tool, "args": args, "summary": summary}
    return Outcome({"pending_confirmation": True, "summary": summary, "note": "Not done yet; the user must press Confirm."},
                   pending=pending, final=f"Please confirm: {summary}.")


def _t_update_requirement_status(ctx, args) -> Outcome:
    cand, problem = _one_candidate(ctx.db, args.get("candidate"))
    if problem:
        return problem
    pos, problem = _one_demand(ctx.db, args.get("demand"))
    if problem:
        return problem
    wanted = next((s for s in REQUIREMENT_STATUSES if s.casefold() == str(args.get("status") or "").strip().casefold()), None)
    if not wanted:
        return Outcome({"error": f"Status must be one of: {', '.join(REQUIREMENT_STATUSES)}."})
    return _pending(ctx, "update_requirement_status", {"candidate_id": cand.id, "position_id": pos.id, "status": wanted},
                    f"set {cand.candidate_name} ({cand.display_id}) to {wanted} for {_demand_label(pos)}")


def _t_set_availability(ctx, args) -> Outcome:
    cand, problem = _one_candidate(ctx.db, args.get("candidate"))
    if problem:
        return problem
    wanted = next((s for s in AVAILABILITY if s.casefold() == str(args.get("availability") or "").strip().casefold()), None)
    if not wanted:
        return Outcome({"error": "Availability must be Active or Not Active."})
    return _pending(ctx, "set_availability", {"candidate_id": cand.id, "availability": wanted},
                    f"mark {cand.candidate_name} ({cand.display_id}) as {wanted}")


def _t_create_demand(ctx, args) -> Outcome:
    from backend.routers import assistant_demand  # imported here: that router imports the job-description router

    details = str(args.get("details") or "").strip()
    session, messages = assistant_demand.begin(ctx.db, ctx.user, ctx.conversation, text=details or None, persist=False)
    return Outcome({"started": True}, ui={"action": "demand_session", "session": assistant_demand.view(ctx.db, session)},
                   final="\n\n".join(m["content"] for m in messages))


def _t_draft_email(ctx, args) -> Outcome:
    pos, problem = _one_demand(ctx.db, args.get("demand"))
    if problem:
        return problem
    return Outcome({"opened": True}, ui={"action": "email", "position_id": pos.id, "position": {"display_id": pos.display_id, "title": pos.title}},
                   final=f"I selected {_demand_label(pos)}. Open Email to review demand-grounded drafts; nothing will be sent automatically.")


_IMPLEMENTATIONS = {name[3:]: fn for name, fn in list(globals().items()) if name.startswith("_t_")}


# ----------------------------------------------------------------------------- the loop

@dataclass
class _Ctx:
    db: Session
    user: User
    conversation: Conversation
    recent: Dict[str, str]


def _history(conversation: Conversation, message: str) -> List[Dict[str, str]]:
    turns = [{"role": m.role, "content": (m.content or "")[:1500]} for m in conversation.messages if m.role in ("user", "assistant")]
    turns = turns[-HISTORY_TURNS:]
    if not turns or turns[-1] != {"role": "user", "content": message[:1500]}:
        turns.append({"role": "user", "content": message[:1500]})
    return turns


def _call(call: dict, ctx: _Ctx) -> Outcome:
    function = call.get("function") or {}
    name = function.get("name") or ""
    try:
        args = json.loads(function.get("arguments") or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError:
        return Outcome({"error": "The tool arguments were not valid JSON."})
    run = _IMPLEMENTATIONS.get(name)
    if run is None:
        return Outcome({"error": f"Unknown tool '{name}'."})
    try:
        return run(ctx, args)
    except Exception as exc:  # a failing tool must not end the chat
        logger.exception("Assistant tool %s failed", name)
        ctx.db.rollback()
        return Outcome({"error": f"The {name} tool failed: {str(exc)[:200]}"})


def run_agent(db: Session, user: User, conversation: Conversation, message: str, position_id: Optional[str] = None) -> Tuple[str, dict]:
    """Let the model pick tools until it has an answer. Returns (reply, ui payload); raises AgentUnavailable."""
    memory = load_memory(db, user)
    current = db.get(Position, position_id) if position_id else None
    messages: List[Dict[str, Any]] = [{"role": "system", "content": build_agent_prompt(memory, _demand_label(current) if current else None)},
                                      *_history(conversation, message)]
    ctx = _Ctx(db, user, conversation, {})
    ui: Optional[dict] = None
    reply = ""
    for _ in range(MAX_ROUNDS):
        try:
            turn = chat_with_tools(messages, TOOLS)
        except Exception as exc:
            raise AgentUnavailable(str(exc)) from exc
        calls = turn.get("tool_calls") or []
        if not calls:
            reply = (turn.get("content") or "").strip()
            break
        messages.append({"role": "assistant", "content": turn.get("content") or "", "tool_calls": calls})
        ended = None
        for call in calls:
            outcome = _call(call, ctx)
            if outcome.ui:
                ui = outcome.ui
            if outcome.pending:
                ui = {"action": "confirm_action", "pending": outcome.pending}
            if ended is None and outcome.final is not None and (outcome.pending or outcome.ui):
                ended = outcome.final
            body = json.dumps(outcome.result, ensure_ascii=False, default=str)[:MAX_RESULT_CHARS]
            messages.append({"role": "tool", "tool_call_id": call.get("id") or "", "content": untrusted(f"tool:{(call.get('function') or {}).get('name')}", body)})
            if outcome.pending:
                break  # one change at a time
        if ended is not None:
            reply = ended
            break
    else:
        reply = "I could not finish that in a few steps. Please narrow the question."
    if ctx.recent:
        _update_memory(db, user, recent=ctx.recent)
    return reply or "I could not find an answer in TruHire. Try rephrasing.", ui or {"action": "reply"}


# ----------------------------------------------------------------------------- confirmation

def _find_pending(conversation: Conversation, pending_id: str) -> Optional[ConversationMessage]:
    for m in reversed(conversation.messages):
        if m.role == "assistant" and ((m.message_data or {}).get("pending") or {}).get("id") == pending_id:
            return m
    return None


def resolve_pending(db: Session, user: User, conversation: Conversation, pending_id: str, approve: bool) -> Tuple[str, dict]:
    """Run (or reject) a confirmed write. The id is single-use: it is consumed before anything executes."""
    msg = _find_pending(conversation, pending_id)
    if msg is None:
        raise HTTPException(404, "That action was not found in this conversation.")
    pending = dict((msg.message_data or {}).get("pending") or {})
    if pending.get("status", "pending") != "pending":
        raise HTTPException(409, "That action was already answered.")
    created = msg.created_at or datetime.utcnow()
    expired = datetime.utcnow() - created > PENDING_TTL
    msg.message_data = {**msg.message_data, "pending": {**pending, "status": "rejected" if (not approve or expired) else "approved"}}
    db.commit()  # consume the id first so a retry or double click cannot run it twice
    tool, args = pending.get("tool"), pending.get("args") or {}
    if expired:
        raise HTTPException(410, "That action expired. Ask me again.")
    if not approve:
        ai_audit.record(provider="agent", feature="assistant_action", status="rejected", details={"tool": tool, "args": args, "pending_id": pending_id})
        return "Okay, I did not make that change.", {"action": "action_rejected", "tool": tool}
    try:
        if tool == "update_requirement_status":
            from backend.routers.job_descriptions import set_requirement_candidate_status

            set_requirement_candidate_status(args["position_id"], args["candidate_id"], args["status"], db, user)
        elif tool == "set_availability":
            from backend.routers.candidates import CandidateAvailabilityUpdateRequest, update_candidate_availability

            update_candidate_availability(args["candidate_id"], CandidateAvailabilityUpdateRequest(status=args["availability"]), db, user)
        else:
            raise HTTPException(400, "Unsupported action.")
    except HTTPException as exc:
        ai_audit.record(provider="agent", feature="assistant_action", status="error", error=str(exc.detail), details={"tool": tool, "args": args})
        return f"I could not do that: {exc.detail}", {"action": "action_failed", "tool": tool}
    ai_audit.record(provider="agent", feature="assistant_action", status="ok", details={"tool": tool, "args": args, "pending_id": pending_id, "user_id": user.id})
    return f"Done: {pending.get('summary')}.", {"action": "action_done", "tool": tool, "args": args}
