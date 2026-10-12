"""Central logging setup: one format everywhere, request-correlated, rotating file + console.

Every record carries `trace_id` (the same id returned to the client in the X-Trace-ID
header and stored in the AI audit trail), so one request can be followed across the API,
search pipeline, LLM calls and background work. Set LOG_JSON=true for structured logs
(ship to OpenSearch/ELK/Datadog), LOG_LEVEL to tune verbosity, LOG_FILE="" to disable the file.
"""
import json
import logging
import logging.handlers
from pathlib import Path

from backend.config import settings

_TEXT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | trace=%(trace_id)s | %(message)s"
_NOISY = {"httpx": "WARNING", "httpcore": "WARNING", "urllib3": "WARNING", "opensearch": "WARNING",
          "multipart": "WARNING", "asyncio": "WARNING", "watchfiles": "WARNING", "fastembed": "WARNING"}
_configured = False


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            try:
                from backend.services.common.ai_audit import _trace_id
                record.trace_id = _trace_id.get() or "system"
            except Exception:
                record.trace_id = "system"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name,
            "trace_id": getattr(record, "trace_id", "system"), "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    formatter: logging.Formatter = JsonFormatter() if settings.LOG_JSON else logging.Formatter(_TEXT_FORMAT)
    handlers = [logging.StreamHandler()]
    if settings.LOG_FILE:
        try:
            path = Path(settings.LOG_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"))
        except OSError as exc:
            logging.getLogger(__name__).warning("File logging disabled (%s): %s", settings.LOG_FILE, exc)

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())
    for existing in list(root.handlers):
        root.removeHandler(existing)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(TraceIdFilter())
        root.addHandler(handler)

    # Route uvicorn's own loggers through the same handlers/format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # uvicorn.access duplicates our per-request line (which also has trace id and user context).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    for name, level in _NOISY.items():
        logging.getLogger(name).setLevel(level)
