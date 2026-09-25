"""Minimal Qdrant REST client used as TruHire's persistent vector database."""
from typing import Any, Dict, List, Optional
import httpx
from backend.config import settings


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.QDRANT_API_KEY:
        headers["api-key"] = settings.QDRANT_API_KEY
    return headers


def _url(path: str) -> str:
    return settings.QDRANT_URL.rstrip("/") + path


def collection_exists() -> bool:
    with httpx.Client(timeout=10) as client:
        response = client.get(_url(f"/collections/{settings.QDRANT_COLLECTION}"), headers=_headers())
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True


def ensure_collection(vector_size: int) -> None:
    if collection_exists():
        with httpx.Client(timeout=10) as client:
            response = client.get(_url(f"/collections/{settings.QDRANT_COLLECTION}"), headers=_headers())
            response.raise_for_status()
            info = response.json().get("result", {})
            configured = info.get("config", {}).get("params", {}).get("vectors", {})
            if isinstance(configured, dict) and configured.get("size") and int(configured["size"]) != int(vector_size):
                raise RuntimeError(
                    f"Qdrant collection '{settings.QDRANT_COLLECTION}' has dimension {configured['size']}, "
                    f"but embedding model returned dimension {vector_size}. Recreate/reindex the collection with the same embedding model."
                )
        return
    payload = {"vectors": {"size": vector_size, "distance": settings.QDRANT_DISTANCE}}
    with httpx.Client(timeout=15) as client:
        response = client.put(
            _url(f"/collections/{settings.QDRANT_COLLECTION}"),
            headers=_headers(), json=payload
        )
        response.raise_for_status()


def upsert_candidate(candidate_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
    ensure_collection(len(vector))
    body = {
        "points": [{"id": candidate_id, "vector": vector, "payload": payload}]
    }
    with httpx.Client(timeout=30) as client:
        response = client.put(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/points?wait=true"),
            headers=_headers(), json=body
        )
        response.raise_for_status()


def delete_candidate(candidate_id: str) -> None:
    if not collection_exists():
        return
    body = {"points": [candidate_id]}
    with httpx.Client(timeout=15) as client:
        response = client.post(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/points/delete?wait=true"),
            headers=_headers(), json=body
        )
        response.raise_for_status()


def search_vectors(query_vector: List[float], top_k: int = 20) -> List[Dict[str, Any]]:
    if not collection_exists():
        return []
    body = {
        "vector": query_vector,
        "limit": top_k,
        "with_payload": True,
        "with_vector": False,
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(
            _url(f"/collections/{settings.QDRANT_COLLECTION}/points/search"),
            headers=_headers(), json=body
        )
        response.raise_for_status()
        data = response.json()
    return [
        {
            "candidate_id": str(item["id"]),
            "score": float(item.get("score", 0.0)),
            "payload": item.get("payload") or {},
        }
        for item in data.get("result", [])
    ]
