import time
from typing import Any, Dict, Optional, Tuple

_cache_store: Dict[str, Tuple[Any, float]] = {}


def get_cache(key: str) -> Optional[Any]:
    """Retrieves item from cache if not expired."""
    entry = _cache_store.get(key)
    if not entry:
        return None

    val, expires_at = entry
    if time.time() > expires_at:
        # Expired
        del _cache_store[key]
        return None
    return val


def set_cache(key: str, val: Any, ttl_seconds: int):
    """Sets item in cache with TTL."""
    _cache_store[key] = (val, time.time() + ttl_seconds)


def clear_cache():
    """Clears all cached items."""
    _cache_store.clear()
