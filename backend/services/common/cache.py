import json
import pickle
import time
from typing import Any, Dict, Optional, Tuple
import redis

from backend.config import settings

_redis_client: Optional[redis.Redis] = None
_redis_init_attempted = False
_in_memory_store: Dict[str, Tuple[Any, float]] = {}


def get_redis_client() -> Optional[redis.Redis]:
    """
    Returns an active Redis client using connection pooling.
    Falls back gracefully to None if Redis is unreachable.
    """
    global _redis_client, _redis_init_attempted
    if _redis_client is not None:
        return _redis_client
    if _redis_init_attempted:
        return None

    _redis_init_attempted = True
    redis_url = settings.effective_redis_url
    if not redis_url:
        return None

    try:
        if settings.REDIS_PASSWORD and settings.REDIS_HOST:
            client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )
        else:
            client = redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )

        if client.ping():
            _redis_client = client
            print(f"[cache] Redis cache initialized successfully ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
            return _redis_client
    except Exception as exc:
        print(f"[cache] Redis connection unavailable, using in-memory TTL cache fallback: {exc}")

    return None


def _serialize(value: Any) -> bytes:
    try:
        return b"json:" + json.dumps(value).encode("utf-8")
    except (TypeError, ValueError):
        return b"pkl:" + pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)


def _deserialize(payload: bytes) -> Any:
    if payload.startswith(b"json:"):
        return json.loads(payload[5:].decode("utf-8"))
    elif payload.startswith(b"pkl:"):
        return pickle.loads(payload[4:])
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return payload.decode("utf-8", errors="ignore")


def get_cache(key: str) -> Optional[Any]:
    """Retrieves item from Redis cache (or in-memory fallback) if not expired."""
    r = get_redis_client()
    if r is not None:
        try:
            val = r.get(key)
            if val is not None:
                return _deserialize(val)
            return None
        except Exception as exc:
            print(f"[cache] Redis get failed for key {key}: {exc}")

    # Fallback to in-memory store
    entry = _in_memory_store.get(key)
    if not entry:
        return None
    val, expires_at = entry
    if time.time() > expires_at:
        del _in_memory_store[key]
        return None
    return val


def set_cache(key: str, val: Any, ttl_seconds: int = 3600):
    """Sets item in Redis cache with TTL (and in-memory fallback)."""
    r = get_redis_client()
    if r is not None:
        try:
            serialized = _serialize(val)
            r.setex(key, ttl_seconds, serialized)
            return
        except Exception as exc:
            print(f"[cache] Redis set failed for key {key}: {exc}")

    # In-memory store fallback
    _in_memory_store[key] = (val, time.time() + ttl_seconds)


def delete_cache(key: str):
    """Deletes an item from both Redis and in-memory cache."""
    r = get_redis_client()
    if r is not None:
        try:
            r.delete(key)
        except Exception as exc:
            print(f"[cache] Redis delete error: {exc}")
    _in_memory_store.pop(key, None)


def clear_cache(prefix: Optional[str] = None):
    """Clears all cached items or all items matching a given prefix."""
    r = get_redis_client()
    if r is not None:
        try:
            if prefix:
                cursor = 0
                while True:
                    cursor, keys = r.scan(cursor=cursor, match=f"{prefix}*", count=100)
                    if keys:
                        r.delete(*keys)
                    if cursor == 0:
                        break
            else:
                r.flushdb()
        except Exception as exc:
            print(f"[cache] Redis clear error: {exc}")

    if prefix:
        for k in list(_in_memory_store.keys()):
            if k.startswith(prefix):
                _in_memory_store.pop(k, None)
    else:
        _in_memory_store.clear()


# ============================================================
# Session Caching (Auth tokens & User profiles)
# ============================================================

def cache_user_session(user_id: str, user_dict: dict, ttl_seconds: Optional[int] = None):
    """Caches authenticated user session data in Redis to prevent repeated DB lookups."""
    ttl = ttl_seconds or settings.CACHE_TTL_SESSION
    set_cache(f"truhire:session:user:{user_id}", user_dict, ttl_seconds=ttl)


def get_cached_user_session(user_id: str) -> Optional[dict]:
    """Retrieves user session data from Redis."""
    return get_cache(f"truhire:session:user:{user_id}")
