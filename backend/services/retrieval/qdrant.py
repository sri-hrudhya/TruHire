"""Minimal Qdrant REST client used as TruHire's persistent vector database."""
import logging
from typing import Any, Dict, List, Optional
import threading
import time
import uuid
import httpx
from backend.config import settings
from backend.services.common.cache import bump_index_epoch
from backend.services.retrieval.filters import SearchFilters, NO_FILTERS, qdrant_filter

logger = logging.getLogger(__name__)


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.QDRANT_API_KEY:
        headers["api-key"] = settings.QDRANT_API_KEY
    return headers


def _url(path: str) -> str:
    return settings.QDRANT_URL.rstrip("/") + path


_http: Optional[httpx.Client] = None
_http_lock = threading.Lock()


def _client() -> httpx.Client:
    """One keep-alive client for the process, so each call skips the TLS handshake to Qdrant Cloud."""
    global _http
    if _http is None:
        with _http_lock:
            if _http is None:
                _http = httpx.Client(timeout=30, limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60))
    return _http


# In-process cache of "collection exists and has the right dimension", so the hot
# search/ingest paths do not make extra HTTP round-trips to Qdrant Cloud on every call.
_state: Dict[str, Any] = {"ok_until": 0.0, "dim": None}


def _invalidate_state() -> None:
    _state["ok_until"] = 0.0
    _state["dim"] = None


def _collection_info() -> Optional[Dict[str, Any]]:
    client = _client()
    response = client.get(_url(f"/collections/{settings.QDRANT_COLLECTION}"), headers=_headers(), timeout=10)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("result", {})


def collection_exists() -> bool:
    if time.time() < _state["ok_until"]:
        return True
    if _collection_info() is None:
        return False
    _state["ok_until"] = time.time() + settings.INDEX_STATE_TTL
    return True


def _collection_body(vector_size: int) -> Dict[str, Any]:
    body: Dict[str, Any] = {"vectors": {"size": vector_size, "distance": settings.QDRANT_DISTANCE, "on_disk": settings.QDRANT_ON_DISK}}
    if settings.QDRANT_QUANTIZATION:
        body["quantization_config"] = {"scalar": {"type": "int8", "quantile": settings.QDRANT_QUANTILE, "always_ram": True}}
    return body


# candidate_id keeps delete-by-filter fast; the others serve the location/role search filters.
# Clusters in strict mode reject filters on unindexed fields. Creating an index is idempotent.
_PAYLOAD_INDEXES = ("candidate_id", "location_keys", "role_tokens")


def _ensure_payload_index() -> None:
    client = _client()
    for field in _PAYLOAD_INDEXES:
        response = client.put(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/index?wait=true"),
            headers=_headers(), json={"field_name": field, "field_schema": "keyword"}, timeout=15,
        )
        response.raise_for_status()


_filter_indexes_ready = False


def _ensure_filter_indexes_once() -> None:
    """Collections created before location/role filters existed lack their payload indexes (only
    needed on strict-mode clusters). Create them lazily on first filtered search; never fail the search."""
    global _filter_indexes_ready
    if _filter_indexes_ready:
        return
    try:
        _ensure_payload_index()
        _filter_indexes_ready = True
    except Exception as exc:
        logger.warning(f"Qdrant filter payload indexes could not be ensured: {exc}")


def ensure_collection(vector_size: int) -> None:
    if time.time() < _state["ok_until"] and _state["dim"] in (None, vector_size):
        return
    info = _collection_info()
    if info is not None:
        configured = info.get("config", {}).get("params", {}).get("vectors", {})
        if isinstance(configured, dict) and configured.get("size") and int(configured["size"]) != int(vector_size):
            raise RuntimeError(
                f"Qdrant collection '{settings.QDRANT_COLLECTION}' has dimension {configured['size']}, "
                f"but embedding model returned dimension {vector_size}. Recreate/reindex the collection with the same embedding model."
            )
    else:
        client = _client()
        response = client.put(_url(f"/collections/{settings.QDRANT_COLLECTION}"), headers=_headers(), json=_collection_body(vector_size))
        response.raise_for_status()
    _ensure_payload_index()
    _state["ok_until"] = time.time() + settings.INDEX_STATE_TTL
    _state["dim"] = vector_size


def recreate_collection(vector_size: int) -> None:
    """Drop and recreate the collection with the current memory-efficient layout.
    Destructive: every candidate must be re-indexed afterwards (POST /api/ingest/reindex)."""
    client = _client()
    response = client.delete(_url(f"/collections/{settings.QDRANT_COLLECTION}?wait=true"), headers=_headers(), timeout=60)
    if response.status_code != 404:
        response.raise_for_status()
    _invalidate_state()
    ensure_collection(vector_size)
    bump_index_epoch()


def collection_layout() -> Dict[str, Any]:
    """Operational snapshot (size, on-disk/quantization status) for health checks."""
    info = _collection_info()
    if info is None:
        return {"exists": False}
    params = info.get("config", {}).get("params", {}).get("vectors", {})
    return {
        "exists": True,
        "points": info.get("points_count"),
        "vectors_on_disk": params.get("on_disk") if isinstance(params, dict) else None,
        "quantization": info.get("config", {}).get("quantization_config"),
        "status": info.get("status"),
    }


def _point_id(candidate_id: str, chunk_index: int) -> str:
    # Deterministic UUIDs so re-indexing a candidate overwrites its own chunks.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{candidate_id}:{chunk_index}"))


def _points(candidate_id: str, vectors: List[List[float]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"id": _point_id(candidate_id, i), "vector": vec, "payload": {**payload, "candidate_id": candidate_id, "chunk_index": i}}
        for i, vec in enumerate(vectors)
    ]


def upsert_candidate(candidate_id: str, vectors: List[List[float]], payload: Dict[str, Any]) -> None:
    upsert_candidates_batch([(candidate_id, vectors, payload)])


def upsert_candidates_batch(items: List[tuple]) -> None:
    """items: (candidate_id, [chunk vectors], payload). Existing points for those
    candidates (including legacy single-vector points) are removed first so a
    re-index never leaves stale chunks behind."""
    items = [i for i in items if i[1]]
    if not items:
        return
    ensure_collection(len(items[0][1][0]))
    delete_candidates_batch([cid for cid, _, _ in items])
    points = [p for cid, vecs, payload in items for p in _points(cid, vecs, payload)]
    client = _client()
    for i in range(0, len(points), 256):
        response = client.put(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/points?wait=true"),
            headers=_headers(), json={"points": points[i:i + 256]}, timeout=60,
        )
        response.raise_for_status()
    bump_index_epoch()


def delete_candidate(candidate_id: str) -> None:
    delete_candidates_batch([candidate_id])


def delete_candidates_batch(candidate_ids: List[str]) -> None:
    if not candidate_ids or not collection_exists():
        return
    body = {"filter": {"must": [{"key": "candidate_id", "match": {"any": list(candidate_ids)}}]}}
    try:
        client = _client()
        response = client.post(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/points/delete?wait=true"),
            headers=_headers(), json=body
        )
        response.raise_for_status()
        bump_index_epoch()
    except Exception as exc:
        logger.warning(f"Qdrant batch delete points note: {exc}")


def search_vectors(query_vector: List[float], top_k: int = 20, filters: SearchFilters = NO_FILTERS) -> List[Dict[str, Any]]:
    """Chunk-level search aggregated to one row per candidate (best chunk wins). Location/role
    filters are applied inside Qdrant, before top-k, so a filtered search is not starved by
    ineligible candidates occupying the result window."""
    if not collection_exists():
        return []
    body: Dict[str, Any] = {"vector": query_vector, "limit": top_k * 4, "with_payload": True, "with_vector": False}
    flt = qdrant_filter(filters)
    if flt:
        body["filter"] = flt
        _ensure_filter_indexes_once()
    if settings.QDRANT_QUANTIZATION:
        body["params"] = {"quantization": {"rescore": True, "oversampling": settings.QDRANT_RESCORE_OVERSAMPLING}}
    client = _client()
    response = client.post(
        _url(f"/collections/{settings.QDRANT_COLLECTION}/points/search"),
        headers=_headers(), json=body
    )
    response.raise_for_status()
    data = response.json()
    best: Dict[str, Dict[str, Any]] = {}
    for item in data.get("result", []):
        payload = item.get("payload") or {}
        cid = str(payload.get("candidate_id") or item["id"])
        score = float(item.get("score", 0.0))
        if cid not in best or score > best[cid]["score"]:
            best[cid] = {"candidate_id": cid, "score": score, "chunk_index": payload.get("chunk_index"), "payload": payload}
    return sorted(best.values(), key=lambda r: r["score"], reverse=True)[:top_k]
