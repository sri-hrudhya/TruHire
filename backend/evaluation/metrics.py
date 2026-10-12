"""Standard ranking-quality metrics for retrieval evaluation. Pure functions, no I/O.

`ranked` is the ordered list of returned candidate ids; `relevance` maps candidate id to a
graded judgement (0 = irrelevant, 1 = relevant, 2 = highly relevant, ...). Anything not in
`relevance` counts as irrelevant.
"""
import math
from statistics import mean
from typing import Dict, List, Sequence


def _rel(relevance: Dict[str, int], cid: str) -> int:
    return int(relevance.get(cid, 0))


def precision_at_k(ranked: Sequence[str], relevance: Dict[str, int], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for cid in ranked[:k] if _rel(relevance, cid) > 0)
    return hits / k


def recall_at_k(ranked: Sequence[str], relevance: Dict[str, int], k: int) -> float:
    total = sum(1 for v in relevance.values() if v > 0)
    if total == 0:
        return 0.0
    return sum(1 for cid in ranked[:k] if _rel(relevance, cid) > 0) / total


def reciprocal_rank(ranked: Sequence[str], relevance: Dict[str, int]) -> float:
    for i, cid in enumerate(ranked, start=1):
        if _rel(relevance, cid) > 0:
            return 1.0 / i
    return 0.0


def dcg_at_k(ranked: Sequence[str], relevance: Dict[str, int], k: int) -> float:
    return sum((2 ** _rel(relevance, cid) - 1) / math.log2(i + 1) for i, cid in enumerate(ranked[:k], start=1))


def ndcg_at_k(ranked: Sequence[str], relevance: Dict[str, int], k: int) -> float:
    ideal = sorted((v for v in relevance.values() if v > 0), reverse=True)
    ideal_dcg = sum((2 ** v - 1) / math.log2(i + 1) for i, v in enumerate(ideal[:k], start=1))
    if ideal_dcg == 0:
        return 0.0
    return dcg_at_k(ranked, relevance, k) / ideal_dcg


def evaluate_query(ranked: Sequence[str], relevance: Dict[str, int], ks: Sequence[int]) -> Dict[str, float]:
    out: Dict[str, float] = {"mrr": reciprocal_rank(ranked, relevance)}
    for k in ks:
        out[f"precision@{k}"] = precision_at_k(ranked, relevance, k)
        out[f"recall@{k}"] = recall_at_k(ranked, relevance, k)
        out[f"ndcg@{k}"] = ndcg_at_k(ranked, relevance, k)
    return out


def aggregate(per_query: List[Dict[str, float]]) -> Dict[str, float]:
    if not per_query:
        return {}
    return {name: round(mean(q[name] for q in per_query), 4) for name in per_query[0]}
