"""
Local, self-contained embedding generation via `fastembed` (Qdrant's own ONNX-based
embedding library). No external API key, no DGX/vLLM dependency — runs entirely inside
this process on CPU. Used when EMBEDDING_PROVIDER=local.
"""
from typing import List

from backend.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=settings.LOCAL_EMBEDDING_MODEL)
    return _model


def generate_embedding(text: str) -> List[float]:
    if not text:
        raise ValueError("Cannot generate an embedding from empty text.")
    model = _get_model()
    vector = next(iter(model.embed([text])))
    return [float(x) for x in vector]


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Embed many texts in one fastembed call. fastembed batches internally and is
    meaningfully faster per-item this way than one generate_embedding() call per text -
    the throughput path used by bulk ingestion."""
    if not texts:
        return []
    model = _get_model()
    return [[float(x) for x in vector] for vector in model.embed(texts)]
