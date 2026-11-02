"""
Shared rate limiter instance. Lives at the top level (alongside auth.py/database.py)
rather than inside services/, since both main.py (global default + exception handler)
and individual routers (tighter per-route limits) need to import it without a circular
dependency on main.py itself.

Requests are counted per signed-in user (taken from the bearer token), and per client IP when there is no
token (login, register). Behind nginx every user would otherwise share the proxy's IP and one common
budget. Counts live in Redis when it is configured, so they are shared by every API worker; if Redis is
unreachable the limiter falls back to per-process counters instead of failing requests.
"""
from urllib.parse import quote

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.config import settings


def client_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            sub = jwt.decode(auth[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]).get("sub")
        except jwt.PyJWTError:
            sub = None
        if sub:
            return f"user:{sub}"
    return get_remote_address(request)


def _storage_uri() -> str | None:
    if not settings.RATE_LIMIT_USE_REDIS:
        return None
    if settings.REDIS_PASSWORD and settings.REDIS_HOST:  # same connection rules as the response cache
        return f"redis://:{quote(settings.REDIS_PASSWORD, safe='')}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
    return settings.effective_redis_url


limiter = Limiter(
    key_func=client_key,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=_storage_uri(),
    in_memory_fallback_enabled=True,
    key_prefix="truhire-rl",
)
