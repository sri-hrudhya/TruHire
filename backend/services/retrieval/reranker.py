"""Cross-encoder reranking (BGE reranker) over the best-matching resume chunk.

Bi-encoder vectors and BM25 are fast but coarse; a cross-encoder reads query and passage
together and is far better at telling a genuine fit from a keyword overlap. It is too slow
for the whole pool, so it only scores a bounded shortlist (settings.RERANKER_POOL_CAP).

Runs in-process via fastembed (ONNX, CPU). Any failure - model download blocked, ONNX
error - disables it for RERANKER_RETRY_SECONDS and search falls back to the un-reranked
ordering instead of failing the request.
"""
import logging
import hashlib
import math
import threading
import time
from typing import List, Optional, Sequence

from backend.config import settings
from backend.services.common.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()
_disabled_until = 0.0


def _get_model():
    global _model
    if _model is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _model = TextCrossEncoder(model_name=settings.RERANKER_MODEL)
    return _model


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _pair_key(query: str, passage: str) -> str:
    digest = hashlib.sha256(f"{settings.RERANKER_MODEL}||{query}||{passage}".encode("utf-8", "ignore")).hexdigest()
    return f"rerank:bge:{digest}"


def rerank_passages(query: str, passages: Sequence[str]) -> Optional[List[float]]:
    """Relevance in [0, 1] per passage (same order), or None when the reranker is
    disabled/unavailable. Pair scores are cached, so repeating a search is free."""
    global _disabled_until
    if not settings.RERANKER_ENABLED or not passages or not query.strip():
        return None
    if time.time() < _disabled_until:
        return None

    scores: List[Optional[float]] = [None] * len(passages)
    todo: List[int] = []
    for i, passage in enumerate(passages):
        cached = get_cache(_pair_key(query, passage))
        if cached is not None:
            scores[i] = float(cached)
        else:
            todo.append(i)

    if todo:
        try:
            with _lock:
                raw = list(_get_model().rerank(query, [passages[i] for i in todo]))
        except Exception as exc:
            _disabled_until = time.time() + settings.RERANKER_RETRY_SECONDS
            logger.warning(f"[reranker] unavailable, falling back to un-reranked order for {settings.RERANKER_RETRY_SECONDS}s: {exc}")
            return None
        for i, logit in zip(todo, raw):
            scores[i] = _sigmoid(float(logit))
            set_cache(_pair_key(query, passages[i]), scores[i], settings.CACHE_TTL_DECISION)

    return [float(s) if s is not None else 0.0 for s in scores]


def blend(deterministic_score: float, rerank_relevance: float) -> float:
    """Blend a 0-100 deterministic score with a 0-1 reranker relevance."""
    w = settings.RERANKER_WEIGHT
    return round((1 - w) * deterministic_score + w * rerank_relevance * 100.0, 1)
