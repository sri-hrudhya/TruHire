import time

import pytest

from backend.database import SessionLocal
from backend.services.common import cache
from backend.services.retrieval import opensearch, qdrant
from backend.services.retrieval import search as search_module


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_repeat_search_skips_embedding_and_indexes(db, monkeypatch):
    cache.clear_cache("search:")
    calls = {"embed": 0, "vectors": 0, "lexical": 0}

    def embed(text):
        calls["embed"] += 1
        return [0.0] * 8

    def vectors(*args, **kwargs):
        calls["vectors"] += 1
        return []

    def lexical(*args, **kwargs):
        calls["lexical"] += 1
        return []

    monkeypatch.setattr(search_module, "generate_embedding", embed)
    monkeypatch.setattr(search_module, "search_vectors", vectors)
    monkeypatch.setattr(search_module, "search_lexical", lexical)

    first = search_module.execute_candidate_search(db, query_text="python engineer cache-perf-test")
    second = search_module.execute_candidate_search(db, query_text="python engineer cache-perf-test")

    assert second == first
    assert calls == {"embed": 1, "vectors": 1, "lexical": 1}


def test_search_results_outlive_the_generic_query_ttl(db, monkeypatch):
    cache.clear_cache("search:")
    seen = []
    monkeypatch.setattr(search_module, "set_cache", lambda key, value, ttl=None: seen.append(ttl))
    monkeypatch.setattr(search_module, "generate_embedding", lambda text: [0.0] * 8)
    monkeypatch.setattr(search_module, "search_vectors", lambda *a, **k: [])
    monkeypatch.setattr(search_module, "search_lexical", lambda *a, **k: [])

    search_module.execute_candidate_search(db, query_text="python engineer ttl-test")

    assert seen == [search_module.settings.CACHE_TTL_SEARCH]
    assert search_module.settings.CACHE_TTL_SEARCH > search_module.settings.CACHE_TTL_QUERY


def test_redis_is_retried_after_the_backoff(monkeypatch):
    class FakeRedis:
        def __init__(self, *args, **kwargs):
            pass

        def ping(self):
            return True

    attempts = {"n": 0}

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("redis down")
        return FakeRedis()

    monkeypatch.setattr(cache, "_redis_client", None)
    monkeypatch.setattr(cache, "_redis_retry_at", 0.0)
    monkeypatch.setattr(cache.redis, "Redis", flaky)
    monkeypatch.setattr(cache.redis, "from_url", flaky)

    assert cache.get_redis_client() is None
    assert cache.get_redis_client() is None and attempts["n"] == 1  # inside the backoff window
    monkeypatch.setattr(cache, "_redis_retry_at", time.time() - 1)
    assert isinstance(cache.get_redis_client(), FakeRedis)


def test_qdrant_reuses_one_http_client():
    assert qdrant._client() is qdrant._client()


def test_opensearch_index_is_checked_once(monkeypatch):
    class FakeIndices:
        exists_calls = 0

        def exists(self, index):
            FakeIndices.exists_calls += 1
            return True

        def put_mapping(self, **kwargs):
            pass

    class FakeClient:
        indices = FakeIndices()

    monkeypatch.setattr(opensearch, "get_opensearch_client", lambda: FakeClient())
    monkeypatch.setattr(opensearch, "_index_ready", False)

    assert opensearch.init_opensearch_index() is True
    assert opensearch.init_opensearch_index() is True
    assert FakeIndices.exists_calls == 1
