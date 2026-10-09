"""
AI audit trail: who asked which model what, what came back, and what the guardrails decided.

Request context (user, trace id) is set once by ObservabilityMiddleware and inherited by
everything the request runs, including threadpool endpoints and background tasks. Call
sites only name the feature with `with ai_feature("search_summary"):`.

Writes go through a single background writer thread. On SQLite the request's own session
often holds the write lock while an LLM call is in flight, so writing inline would stall
the request; queueing keeps auditing off the request path and the writer simply commits
once the lock is free. Auditing is best-effort: a failed write is logged, never raised.
"""
import contextvars
import hashlib
import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger("truhire.ai_audit")

PREVIEW_CHARS = 2000

_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ai_audit_user_id", default=None)
_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ai_audit_trace_id", default=None)
_feature: contextvars.ContextVar[str] = contextvars.ContextVar("ai_audit_feature", default="unspecified")

_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_writer_lock = threading.Lock()
_writer: Optional[threading.Thread] = None


def set_request_context(user_id: Optional[str], trace_id: Optional[str]) -> None:
    _user_id.set(user_id)
    _trace_id.set(trace_id)


def set_user(user_id: Optional[str]) -> None:
    _user_id.set(user_id)


@contextmanager
def ai_feature(name: str):
    token = _feature.set(name)
    try:
        yield
    finally:
        _feature.reset(token)


def current_feature() -> str:
    return _feature.get()


def _preview(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    from backend.services.ingestion.pii import redact_pii
    return redact_pii(text[: PREVIEW_CHARS * 2])[:PREVIEW_CHARS]


def record(
    *,
    provider: str,
    status: str = "ok",
    model: Optional[str] = None,
    prompt: Optional[str] = None,
    output: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    latency_ms: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    feature: Optional[str] = None,
) -> None:
    try:
        event = {
            "trace_id": _trace_id.get(),
            "user_id": _user_id.get(),
            "feature": feature or _feature.get(),
            "provider": provider,
            "model": model,
            "status": status,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8", "ignore")).hexdigest() if prompt else None,
            "prompt_preview": _preview(prompt),
            "output_preview": _preview(output),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "details": details,
            "error": (error or "")[:2000] or None,
        }
        _ensure_writer()
        _queue.put(event)
    except Exception as exc:  # never let auditing break the AI feature itself
        logger.error("AI audit event dropped: %s", exc)


def flush(timeout: float = 10.0) -> None:
    """Block until queued events are written (tests, shutdown)."""
    done = threading.Event()

    def _wait():
        _queue.join()
        done.set()

    threading.Thread(target=_wait, daemon=True).start()
    done.wait(timeout)


def _ensure_writer() -> None:
    global _writer
    if _writer and _writer.is_alive():
        return
    with _writer_lock:
        if _writer and _writer.is_alive():
            return
        _writer = threading.Thread(target=_write_loop, name="ai-audit-writer", daemon=True)
        _writer.start()


def _write_loop() -> None:
    from backend.database import SessionLocal
    from backend.models import AIAuditEvent

    while True:
        event = _queue.get()
        try:
            for attempt in range(3):
                db = SessionLocal()
                try:
                    db.add(AIAuditEvent(**event))
                    db.commit()
                    break
                except Exception as exc:
                    db.rollback()
                    # SQLite single-writer contention: wait for the request transaction to finish.
                    if "locked" in str(exc).lower() and attempt < 2:
                        time.sleep(1.0)
                        continue
                    logger.error("AI audit write failed (%s): %s", event.get("feature"), exc)
                    break
                finally:
                    db.close()
        finally:
            _queue.task_done()
