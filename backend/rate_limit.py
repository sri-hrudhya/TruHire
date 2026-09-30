"""
Shared rate limiter instance. Lives at the top level (alongside auth.py/database.py)
rather than inside services/, since both main.py (global default + exception handler)
and individual routers (tighter per-route limits) need to import it without a circular
dependency on main.py itself.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])
