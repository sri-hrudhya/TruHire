"""Offline retrieval evaluation against a labelled dataset.

    python -m backend.scripts.eval_retrieval --dataset eval/retrieval_dataset.json
    python -m backend.scripts.eval_retrieval --dataset eval/retrieval_dataset.json --compare-reranker --out eval/report.json

Dataset format (see eval/retrieval_dataset.example.json): a list of queries, each with an
optional `position_id` (JD) and `relevant`, a map of resume `original_filename` (or candidate
id) to a grade (1 = relevant, 2 = highly relevant). Runs the real search pipeline, so it
needs the same services (.env, Qdrant, OpenSearch, embedding model) as the app.

Use --compare-reranker to run every query twice - with and without the BGE reranker - and
print both side by side, so any change to chunking, weights or models is judged on data
instead of by eye. Exits non-zero if --min-ndcg is given and not met (CI gate).
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from backend.config import settings
from backend.database import SessionLocal
from backend.evaluation.metrics import aggregate, evaluate_query
from backend.models import Candidate
from backend.services.common.cache import bump_index_epoch
from backend.services.retrieval.search import execute_candidate_search


def _load(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["queries"] if isinstance(data, dict) else data


def _relevance_by_id(db, relevant: Dict[str, int]) -> Dict[str, int]:
    """Resolve labels given as filenames or candidate ids to candidate ids."""
    by_name = {c.original_filename: c.id for c in db.query(Candidate.id, Candidate.original_filename).all() if c.original_filename}
    resolved: Dict[str, int] = {}
    for key, grade in relevant.items():
        cid = by_name.get(key, key)
        resolved[cid] = int(grade)
    return resolved


def run(dataset: List[Dict[str, Any]], ks: List[int], top_n: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        per_query, details = [], []
        for item in dataset:
            relevance = _relevance_by_id(db, item.get("relevant", {}))
            result = execute_candidate_search(
                db, item.get("query", ""), item.get("filter_skills"), item.get("min_experience"),
                item.get("position_id"), top_n,
            )
            ranked = [r["candidate"]["id"] for r in result["results"]]
            metrics = evaluate_query(ranked, relevance, ks)
            per_query.append(metrics)
            details.append({"query": item.get("query", ""), "position_id": item.get("position_id"), **{k: round(v, 4) for k, v in metrics.items()}})
        return {"summary": aggregate(per_query), "queries": details}
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--k", type=int, nargs="+", default=[5, 10])
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--compare-reranker", action="store_true", help="Run with and without the BGE reranker.")
    parser.add_argument("--min-ndcg", type=float, default=None, help="Fail (exit 1) if mean nDCG@max(k) is below this.")
    parser.add_argument("--out", help="Write the full JSON report here.")
    args = parser.parse_args()

    dataset = _load(args.dataset)
    report: Dict[str, Any] = {}
    modes = [("reranker_on", True), ("reranker_off", False)] if args.compare_reranker else [("current", settings.RERANKER_ENABLED)]
    original = settings.RERANKER_ENABLED
    try:
        for name, enabled in modes:
            settings.RERANKER_ENABLED = enabled
            bump_index_epoch()  # new epoch -> no cached result from the other mode is reused
            report[name] = run(dataset, args.k, args.top_n)
    finally:
        settings.RERANKER_ENABLED = original

    for name, result in report.items():
        print(f"\n== {name} ({len(dataset)} queries) ==")
        for metric, value in result["summary"].items():
            print(f"  {metric:<14} {value:.4f}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nFull report written to {args.out}")

    if args.min_ndcg is not None:
        key = f"ndcg@{max(args.k)}"
        score = list(report.values())[0]["summary"].get(key, 0.0)
        if score < args.min_ndcg:
            print(f"FAIL: {key} {score:.4f} < required {args.min_ndcg}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
