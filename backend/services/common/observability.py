import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Handlers, format and trace-id injection are configured once in backend/logging_config.py.
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
        user_id = _token_subject(request)
        set_request_context(user_id, trace_id)
        try:
            response: Response = await call_next(request)
        except Exception:
            duration = round((time.time() - start) * 1000, 2)
            logger.exception("UNHANDLED %s %s user=%s duration_ms=%s", request.method, request.url.path, user_id or "-", duration, extra={"trace_id": trace_id})
            return Response("Internal server error", status_code=500, headers={"X-Trace-ID": trace_id})
        duration = round((time.time() - start) * 1000, 2); response.headers["X-Trace-ID"] = trace_id
        from backend.config import settings
        level = logging.ERROR if response.status_code >= 500 else logging.WARNING if (response.status_code >= 400 or duration > settings.SLOW_REQUEST_MS) else logging.INFO
        logger.log(level, "%s %s status=%s duration_ms=%s user=%s%s", request.method, request.url.path, response.status_code, duration, user_id or "-",
                   " SLOW" if duration > settings.SLOW_REQUEST_MS else "", extra={"trace_id": trace_id})
        return response
