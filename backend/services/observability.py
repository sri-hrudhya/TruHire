import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [trace_id=%(trace_id)s] %(message)s"
)
logger = logging.getLogger("truhire")


class TraceIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "trace_id"):
            record.trace_id = "system"
        return True


logger.addFilter(TraceIdFilter())


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        start_time = time.time()

        response: Response = await call_next(request)

        duration = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id

        # Log structured request summary
        logger.info(
            f"{request.method} {request.url.path} status={response.status_code} duration_ms={duration}",
            extra={"trace_id": trace_id}
        )
        return response
