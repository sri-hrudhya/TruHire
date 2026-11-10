import logging
import json
import pickle
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple
import redis

from backend.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_redis_retry_at = 0.0
_REDIS_RETRY_SECONDS = 30
_in_memory_store: "OrderedDict[str, Tuple[Any, float]]" = OrderedDict()
_MAX_MEMORY_ENTRIES = 5000


def get_redis_client() -> Optional[redis.Redis]:
    """
    Returns an active Redis client using connection pooling.
    Falls back to None while Redis is unreachable and retries every _REDIS_RETRY_SECONDS.
    """
    global _redis_client, _redis_retry_at
    if _redis_client is not None:
        return _redis_client
    if time.time() < _redis_retry_at:
        return None

    _redis_retry_at = time.time() + _REDIS_RETRY_SECONDS
    redis_url = settings.effective_cache_redis_url
    if not redis_url:
        return None

    try:
        if settings.REDIS_PASSWORD and settings.REDIS_HOST and not settings.CACHE_REDIS_URL:
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
            logger.info(f"[cache] Redis cache initialized successfully ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
            return _redis_client
    except Exception as exc:
        logger.warning(f"[cache] Redis connection unavailable, using in-memory TTL cache fallback: {exc}")

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
            logger.warning(f"[cache] Redis get failed for key {key}: {exc}")

    # Fallback to in-memory store
    entry = _in_memory_store.get(key)
    if not entry:
        return None
    val, expires_at = entry
    if time.time() > expires_at:
        del _in_memory_store[key]
        return None
    _in_memory_store.move_to_end(key)
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
            logger.warning(f"[cache] Redis set failed for key {key}: {exc}")

    # In-memory store fallback
    now = time.time()
    # Expire stale entries before eviction, then enforce a hard process-local bound.
    for stale_key, (_, expiry) in list(_in_memory_store.items()):
        if expiry <= now:
            _in_memory_store.pop(stale_key, None)
    _in_memory_store[key] = (val, now + max(1, ttl_seconds))
    _in_memory_store.move_to_end(key)
    while len(_in_memory_store) > _MAX_MEMORY_ENTRIES:
        _in_memory_store.popitem(last=False)


def delete_cache(key: str):
    """Deletes an item from both Redis and in-memory cache."""
    r = get_redis_client()
    if r is not None:
        try:
            r.delete(key)
        except Exception as exc:
            logger.warning(f"[cache] Redis delete error: {exc}")
    _in_memory_store.pop(key, None)


def clear_cache(prefix: Optional[str] = None):
    """Clears all cached items or all items matching a given prefix. Also bumps the data epoch, so
    epoch-keyed entries (analytics, ingestion history) are invalidated by every data change."""
    bump_data_epoch()
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
                # Not flushdb(): the same Redis also holds queued ingestion jobs (arq:*) and rate-limit counters.
                cursor = 0
                while True:
                    cursor, keys = r.scan(cursor=cursor, match="*", count=200)
                    doomed = [k for k in keys if not k.startswith((b"arq:", b"truhire-rl", b"LIMITER", b"truhire:lock:"))]
                    if doomed:
                        r.delete(*doomed)
                    if cursor == 0:
                        break
        except Exception as exc:
            logger.warning(f"[cache] Redis clear error: {exc}")

    if prefix:
        for k in list(_in_memory_store.keys()):
            if k.startswith(prefix):
                _in_memory_store.pop(k, None)
    else:
        _in_memory_store.clear()


# ============================================================
# Index-state versioning
# ============================================================
# Search results depend on what is in the vector/lexical indexes. Every index write bumps
# this epoch, and the search cache key embeds it, so a cached result can never outlive the
# index state it was computed from (no prefix scans; safe across several API workers when
# Redis is available).
_INDEX_EPOCH_KEY = "truhire:index_epoch"
_EPOCH_TTL = 10 * 365 * 24 * 3600


def get_index_epoch() -> str:
    return str(get_cache(_INDEX_EPOCH_KEY) or "0")


def bump_index_epoch() -> str:
    epoch = str(time.time_ns())
    set_cache(_INDEX_EPOCH_KEY, epoch, ttl_seconds=_EPOCH_TTL)
    return epoch


# Data epoch: bumped by every clear_cache() call (all write paths already call it), embedded in the
# keys of aggregate endpoints so they can never serve numbers older than the last data change.
_DATA_EPOCH_KEY = "truhire:data_epoch"


def get_data_epoch() -> str:
    return str(get_cache(_DATA_EPOCH_KEY) or "0")


def bump_data_epoch() -> str:
    epoch = str(time.time_ns())
    set_cache(_DATA_EPOCH_KEY, epoch, ttl_seconds=_EPOCH_TTL)
    return epoch
