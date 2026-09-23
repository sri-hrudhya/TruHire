import socket
import numpy as np
from typing import Dict, Any, List, Optional
from opensearchpy import OpenSearch
from backend.config import settings

# In-memory vector store fallback
_in_memory_index: Dict[str, Dict[str, Any]] = {}
_opensearch_checked = False
_opensearch_client_cached: Optional[OpenSearch] = None


def _is_port_open(host: str, port: int, timeout: float = 0.1) -> bool:
    """Fast check if host:port is listening without retries."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_opensearch_client() -> Optional[OpenSearch]:
    """Attempts to connect to OpenSearch cluster with fast failover."""
    global _opensearch_checked, _opensearch_client_cached
    if _opensearch_checked:
        return _opensearch_client_cached

    _opensearch_checked = True
    try:
        # Parse URL
        clean_url = settings.OPENSEARCH_URL.replace("http://", "").replace("https://", "").split("/")[0]
        host, port = clean_url.split(":") if ":" in clean_url else (clean_url, 9200)

        # Fast socket probe
        if not _is_port_open(host, int(port), timeout=0.1):
            _opensearch_client_cached = None
            return None

        client = OpenSearch(
            hosts=[settings.OPENSEARCH_URL],
            http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False,
            timeout=1,
            max_retries=0
        )
        if client.ping():
            _opensearch_client_cached = client
            return client
    except Exception:
        pass

    _opensearch_client_cached = None
    return None


def init_opensearch_index():
    """Initializes the OpenSearch index with KNN mapping if cluster available."""
    client = get_opensearch_client()
    if not client:
        return

    index_name = settings.OPENSEARCH_INDEX
    try:
        if not client.indices.exists(index=index_name):
            mapping = {
                "settings": {
                    "index": {
                        "knn": True,
                        "number_of_shards": 1,
                        "number_of_replicas": 0
                    }
                },
                "mappings": {
                    "properties": {
                        "candidate_id": {"type": "keyword"},
                        "vector": {
                            "type": "knn_vector",
                            "dimension": settings.EMBEDDING_DIM,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib"
                            }
                        },
                        "skills": {"type": "keyword"},
                        "years_experience": {"type": "float"},
                        "candidate_name": {"type": "text"}
                    }
                }
            }
            client.indices.create(index=index_name, body=mapping)
            print(f"Created OpenSearch index {index_name}")
    except Exception as e:
        print(f"Error creating OpenSearch index: {e}")


def index_candidate(candidate_id: str, vector: List[float], metadata: Dict[str, Any]) -> str:
    """
    Indexes candidate vector and metadata.
    Uses OpenSearch if live, or falls back to in-memory store.
    """
    doc = {
        "candidate_id": candidate_id,
        "vector": vector,
        "skills": metadata.get("skills", []),
        "years_experience": metadata.get("years_experience", 0.0),
        "candidate_name": metadata.get("candidate_name", ""),
        "metadata": metadata
    }

    client = get_opensearch_client()
    if client:
        try:
            res = client.index(index=settings.OPENSEARCH_INDEX, id=candidate_id, body=doc, refresh=True)
            return res["_id"]
        except Exception:
            pass

    # In-memory storage
    _in_memory_index[candidate_id] = doc
    return candidate_id


def delete_candidate(candidate_id: str) -> bool:
    """Removes a candidate from the vector store."""
    client = get_opensearch_client()
    if client:
        try:
            client.delete(index=settings.OPENSEARCH_INDEX, id=candidate_id, refresh=True)
        except Exception:
            pass

    if candidate_id in _in_memory_index:
        del _in_memory_index[candidate_id]
    return True


def search_vectors(
    query_vector: List[float],
    top_k: int = 20,
    filter_skills: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Performs kNN vector similarity search.
    Returns list of dicts: {"candidate_id": str, "score": float, "metadata": dict}
    """
    client = get_opensearch_client()
    if client:
        try:
            query_body = {
                "size": top_k,
                "query": {
                    "knn": {
                        "vector": {
                            "vector": query_vector,
                            "k": top_k
                        }
                    }
                }
            }
            if filter_skills:
                query_body["query"] = {
                    "bool": {
                        "must": [
                            {"terms": {"skills": [s.lower() for s in filter_skills]}}
                        ],
                        "filter": {
                            "knn": {
                                "vector": {
                                    "vector": query_vector,
                                    "k": top_k
                                }
                            }
                        }
                    }
                }

            response = client.search(index=settings.OPENSEARCH_INDEX, body=query_body)
            results = []
            for hit in response["hits"]["hits"]:
                results.append({
                    "candidate_id": hit["_source"]["candidate_id"],
                    "score": float(hit["_score"]),
                    "metadata": hit["_source"].get("metadata", {})
                })
            return results
        except Exception:
            pass

    # Fallback to in-memory cosine similarity
    if not _in_memory_index:
        return []

    q_vec = np.array(query_vector, dtype=np.float32)
    q_norm = np.linalg.norm(q_vec)
    if q_norm == 0:
        return []

    scored_candidates = []
    for cid, doc in _in_memory_index.items():
        doc_skills = [s.lower() for s in doc.get("skills", [])]
        if filter_skills:
            if not any(f.lower() in doc_skills for f in filter_skills):
                continue

        d_vec = np.array(doc["vector"], dtype=np.float32)
        d_norm = np.linalg.norm(d_vec)
        if d_norm > 0:
            sim = float(np.dot(q_vec, d_vec) / (q_norm * d_norm))
            # Rescale cosine [-1, 1] to [0, 1]
            sim_score = max(0.0, min(1.0, (sim + 1.0) / 2.0))
        else:
            sim_score = 0.0

        scored_candidates.append({
            "candidate_id": cid,
            "score": sim_score,
            "metadata": doc.get("metadata", {})
        })

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    return scored_candidates[:top_k]
