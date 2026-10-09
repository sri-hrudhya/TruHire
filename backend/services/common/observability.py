import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "trace_id"): record.trace_id = "system"
        return True

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for handler in root_logger.handlers:
    handler.addFilter(TraceIdFilter())
logger = logging.getLogger("truhire")

def _token_subject(request: Request):
    """User id from the Bearer token, for audit context only (endpoints still authenticate via get_current_user)."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        from jose import jwt
        from backend.config import settings
        return jwt.decode(auth[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]).get("sub")
    except Exception:
        return None


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Server-generated so audit records can't be forged or collided via a client header.
        trace_id = str(uuid.uuid4()); request.state.trace_id = trace_id; start = time.time()
        # Set before call_next so the endpoint (and its threadpool/background tasks) inherit it.
        from backend.services.common.ai_audit import set_request_context
        set_request_context(_token_subject(request), trace_id)
        response: Response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2); response.headers["X-Trace-ID"] = trace_id
        logger.info(f"{request.method} {request.url.path} status={response.status_code} duration_ms={duration}", extra={"trace_id": trace_id})
        return response
