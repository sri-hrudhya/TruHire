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

class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4())); request.state.trace_id = trace_id; start = time.time()
        response: Response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2); response.headers["X-Trace-ID"] = trace_id
        logger.info(f"{request.method} {request.url.path} status={response.status_code} duration_ms={duration}", extra={"trace_id": trace_id})
        return response
