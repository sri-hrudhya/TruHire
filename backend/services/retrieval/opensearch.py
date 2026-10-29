"""OpenSearch lexical/BM25 retrieval layer for hybrid search."""
import logging
import time
from typing import Any, Dict, List, Optional
from opensearchpy import OpenSearch
from backend.config import settings
from backend.services.common.cache import bump_index_epoch
from backend.services.retrieval.filters import SearchFilters, NO_FILTERS, opensearch_filters

logger = logging.getLogger(__name__)

_client: Optional[OpenSearch] = None
# When OpenSearch is down, don't re-ping (4s+ each) on every call; retry after a cooldown.
_RETRY_COOLDOWN_SEC = 60
_down_until = 0.0

# Mapping for the filterable fields. Added to indexes created before they existed (put_mapping only
# adds fields), once per process; existing documents gain values when re-indexed.
_FILTER_PROPERTIES = {
    "location": {"type": "text"},
    "location_keys": {"type": "keyword"},
    "job_titles": {"type": "text"},
    "role_tokens": {"type": "keyword"},
}
_mapping_synced = False
_index_ready = False


def get_opensearch_client() -> Optional[OpenSearch]:
    global _client, _down_until
    if _client is not None:
        return _client
    if time.monotonic() < _down_until:
        return None
    try:
        kwargs: Dict[str, Any] = {
            "hosts": [settings.OPENSEARCH_URL],
            "use_ssl": settings.OPENSEARCH_URL.startswith("https://"),
            "verify_certs": False,
            "ssl_show_warn": False,
            "timeout": 5,
            "max_retries": 1,
            "retry_on_timeout": True,
        }
        if settings.OPENSEARCH_USER:
            kwargs["http_auth"] = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD or "")
        client = OpenSearch(**kwargs)
        if client.ping():
            _client = client
            return client
        logger.warning(f"OpenSearch not responding at {settings.OPENSEARCH_URL}; lexical search disabled, retrying in {_RETRY_COOLDOWN_SEC}s")
    except Exception as exc:
        logger.warning(f"OpenSearch unavailable: {exc}")
    _down_until = time.monotonic() + _RETRY_COOLDOWN_SEC
    return None


def init_opensearch_index() -> bool:
    global _index_ready
    client = get_opensearch_client()
    if not client:
        return False
    if _index_ready:
        return True
    index = settings.OPENSEARCH_INDEX
    try:
        if not client.indices.exists(index=index):
            client.indices.create(index=index, body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {"properties": {
                    "candidate_id": {"type": "keyword"},
                    "candidate_name": {"type": "text"},
                    "search_text": {"type": "text"},
                    "skills": {"type": "keyword"},
                    "years_experience": {"type": "float"},
                    **_FILTER_PROPERTIES,
                }}
            })
        else:
            _sync_filter_mapping(client, index)
        _index_ready = True
        return True
    except Exception as exc:
        logger.warning(f"OpenSearch index initialization failed: {exc}")
        return False


def _sync_filter_mapping(client: OpenSearch, index: str) -> None:
    global _mapping_synced
    if _mapping_synced:
        return
    client.indices.put_mapping(index=index, body={"properties": _FILTER_PROPERTIES})
    _mapping_synced = True


def _candidate_doc(candidate_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_name": metadata.get("candidate_name", ""),
        "search_text": metadata.get("search_text", ""),
        "skills": metadata.get("skills", []),
        "years_experience": float(metadata.get("years_experience", 0.0)),
        "location": metadata.get("location", ""),
        "location_keys": metadata.get("location_keys", []),
        "job_titles": metadata.get("job_titles", []),
        "role_tokens": metadata.get("role_tokens", []),
    }


def index_candidate(candidate_id: str, metadata: Dict[str, Any]) -> str:
    client = get_opensearch_client()
    if not client:
        return candidate_id
    init_opensearch_index()
    doc = _candidate_doc(candidate_id, metadata)
    res = client.index(index=settings.OPENSEARCH_INDEX, id=candidate_id, body=doc, refresh=True)
    return str(res["_id"])


def index_candidates_batch(items: List[tuple]) -> None:
    """Batched form of index_candidate: items is a list of (candidate_id, metadata)
    tuples, indexed via the OpenSearch bulk API in one request instead of one HTTP
    call per candidate. Used by bulk ingestion. No-ops (like index_candidate) if
    OpenSearch is unreachable."""
    if not items:
        return
    client = get_opensearch_client()
    if not client:
        return
    init_opensearch_index()
    from opensearchpy import helpers
    actions = [
        {"_index": settings.OPENSEARCH_INDEX, "_id": candidate_id, "_source": _candidate_doc(candidate_id, metadata)}
        for candidate_id, metadata in items
    ]
    helpers.bulk(client, actions, refresh=True)
    bump_index_epoch()


def delete_candidate(candidate_id: str) -> None:
    delete_candidates_batch([candidate_id])


def delete_candidates_batch(candidate_ids: List[str]) -> None:
    if not candidate_ids:
        return
    client = get_opensearch_client()
    if not client:
        return
    try:
        from opensearchpy import helpers
        actions = [
            {"_op_type": "delete", "_index": settings.OPENSEARCH_INDEX, "_id": cid}
            for cid in candidate_ids
        ]
        helpers.bulk(client, actions, refresh=True, ignore_status=[404])
        bump_index_epoch()
    except Exception as exc:
        logger.warning(f"OpenSearch batch delete note: {exc}")


def search_lexical(query_text: str, top_k: int = 50, filter_skills: Optional[List[str]] = None, min_experience: Optional[float] = None, filters: SearchFilters = NO_FILTERS) -> List[Dict[str, Any]]:
    client = get_opensearch_client()
    if not client or not query_text.strip():
        return []
    init_opensearch_index()
    must = [{"multi_match": {
        "query": query_text,
        "fields": ["search_text^4", "candidate_name^2", "skills^3"],
        "type": "best_fields",
        "operator": "or"
    }}]
    clauses: List[Dict[str, Any]] = []
    if filter_skills:
        clauses.append({"terms": {"skills": filter_skills}})
    if min_experience is not None:
        clauses.append({"range": {"years_experience": {"gte": min_experience}}})
    clauses.extend(opensearch_filters(filters))
    body = {"size": top_k, "query": {"bool": {"must": must, "filter": clauses}}}
    try:
        response = client.search(index=settings.OPENSEARCH_INDEX, body=body)
    except Exception as exc:
        logger.warning(f"OpenSearch lexical search failed: {exc}")
        return []
    return [
        {"candidate_id": hit["_source"]["candidate_id"], "score": float(hit.get("_score", 0.0))}
        for hit in response["hits"]["hits"]
    ]
