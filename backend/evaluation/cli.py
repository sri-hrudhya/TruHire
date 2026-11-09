"""Execute a protected retrieval judgment set against the configured search stack.

Usage: python -m backend.evaluation.cli path/to/judgments.jsonl
The input should be access-controlled and contain IDs and grades only, never resume content.
"""
from __future__ import annotations

import argparse
import json
import sys

from backend.database import SessionLocal
from backend.evaluation.runner import evaluate_cases, load_cases
from backend.services.retrieval.client_search import search_client_requirements
from backend.services.retrieval.search import execute_candidate_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate candidate retrieval against human relevance labels.")
    parser.add_argument("dataset", help="Protected JSONL file of judged queries")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.dataset)
        db = SessionLocal()
        try:
            def search(case):
                if case.get("client_name"):
                    result = search_client_requirements(db, case["client_name"], case["query"], top_n=50,
                                                        demand_id=case.get("demand_id"),
                                                        position_id=case.get("position_id"))
                    return [item["candidate"]["id"] for group in result.get("client_groups", [])
                            for item in group["results"]]
                result = execute_candidate_search(db, query_text=case["query"],
                                                  position_id=case.get("position_id"),
                                                  demand_id=case.get("demand_id"), top_n=50)
                return [item["candidate"]["id"] for item in result.get("results", [])]

            print(json.dumps(evaluate_cases(cases, search), indent=2, sort_keys=True))
        finally:
            db.close()
    except (OSError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
