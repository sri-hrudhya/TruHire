"""OpenSearch lexical/BM25 retrieval layer for hybrid search."""
from typing import Any, Dict, List, Optional
from opensearchpy import OpenSearch
from backend.config import settings

_client: Optional[OpenSearch] = None


def get_opensearch_client() -> Optional[OpenSearch]:
    global _client
    if _client is not None:
        return _client
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
    except Exception as exc:
        print(f"OpenSearch unavailable: {exc}")
    return None


def init_opensearch_index() -> bool:
    client = get_opensearch_client()
    if not client:
        return False
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
                }}
            })
        return True
    except Exception as exc:
        print(f"OpenSearch index initialization failed: {exc}")
        return False


def index_candidate(candidate_id: str, metadata: Dict[str, Any]) -> str:
    client = get_opensearch_client()
    if not client:
        return candidate_id
    init_opensearch_index()
    doc = {
        "candidate_id": candidate_id,
        "candidate_name": metadata.get("candidate_name", ""),
        "search_text": metadata.get("search_text", ""),
        "skills": metadata.get("skills", []),
        "years_experience": float(metadata.get("years_experience", 0.0)),
    }
    res = client.index(index=settings.OPENSEARCH_INDEX, id=candidate_id, body=doc, refresh=True)
    return str(res["_id"])


def delete_candidate(candidate_id: str) -> None:
    client = get_opensearch_client()
    if not client:
        return
    try:
        client.delete(index=settings.OPENSEARCH_INDEX, id=candidate_id, refresh=True)
    except Exception:
        pass


def search_lexical(query_text: str, top_k: int = 50, filter_skills: Optional[List[str]] = None, min_experience: Optional[float] = None) -> List[Dict[str, Any]]:
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
    filters: List[Dict[str, Any]] = []
    if filter_skills:
        filters.append({"terms": {"skills": filter_skills}})
    if min_experience is not None:
        filters.append({"range": {"years_experience": {"gte": min_experience}}})
    body = {"size": top_k, "query": {"bool": {"must": must, "filter": filters}}}
    try:
        response = client.search(index=settings.OPENSEARCH_INDEX, body=body)
    except Exception as exc:
        print(f"OpenSearch lexical search failed: {exc}")
        return []
    return [
        {"candidate_id": hit["_source"]["candidate_id"], "score": float(hit.get("_score", 0.0))}
        for hit in response["hits"]["hits"]
    ]
