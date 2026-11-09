"""Run ranking-quality metrics over a protected, human-judged JSONL dataset."""
from __future__ import annotations

import json
import time
from statistics import median
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from backend.evaluation.metrics import aggregate, evaluate_query

_ALLOWED_FIELDS = {"id", "category", "query", "position_id", "demand_id", "client_name", "relevance"}
_MAX_GRADE = 3


def _validate_case(case: Any, line_number: int | None = None) -> dict[str, Any]:
    where = f" on line {line_number}" if line_number is not None else ""
    if not isinstance(case, dict):
        raise ValueError(f"Evaluation case{where} must be a JSON object.")
    forbidden = set(case) - _ALLOWED_FIELDS
    if forbidden:
        raise ValueError(f"Evaluation case{where} contains unsupported field: {sorted(forbidden)[0]}.")
    if not isinstance(case.get("id"), str) or not case["id"].strip():
        raise ValueError(f"Evaluation case{where} requires a non-empty id.")
    if not isinstance(case.get("query"), str) or not case["query"].strip():
        raise ValueError(f"Evaluation case {case['id']!r} requires a non-empty query.")
    if not isinstance(case.get("category"), str) or not case["category"].strip():
        raise ValueError(f"Evaluation case {case['id']!r} requires a category.")
    relevance = case.get("relevance")
    if not isinstance(relevance, dict) or not relevance:
        raise ValueError(f"Evaluation case {case['id']!r} requires a non-empty relevance mapping.")
    for candidate_id, grade in relevance.items():
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ValueError(f"Evaluation case {case['id']!r} has an invalid candidate id.")
        if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= _MAX_GRADE:
            raise ValueError(f"Evaluation case {case['id']!r} relevance grades must be integers from 0 to {_MAX_GRADE}.")
    for field in ("position_id", "demand_id", "client_name"):
        if field in case and case[field] is not None and not isinstance(case[field], str):
            raise ValueError(f"Evaluation case {case['id']!r} field {field} must be a string.")
    return case


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL judgments while rejecting candidate documents and other unreviewed fields."""
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as source:
        for line_number, raw in enumerate(source, start=1):
            if not raw.strip():
                continue
            try:
                case = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in evaluation dataset on line {line_number}.") from exc
            case = _validate_case(case, line_number)
            if case["id"] in seen:
                raise ValueError(f"Duplicate evaluation case id on line {line_number}.")
            seen.add(case["id"])
            cases.append(case)
    if not cases:
        raise ValueError("Evaluation dataset contains no cases.")
    return cases


def evaluate_cases(
    cases: Iterable[Mapping[str, Any]],
    search: Callable[[Mapping[str, Any]], Sequence[str]],
    ks: Sequence[int] = (10, 50),
) -> dict[str, Any]:
    """Evaluate ordered candidate ids returned for each case and summarize by category."""
    rows: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, float]]] = {}
    by_category_latency: dict[str, list[float]] = {}
    seen: set[str] = set()
    for raw_case in cases:
        case = _validate_case(dict(raw_case))
        if case["id"] in seen:
            raise ValueError(f"Duplicate evaluation case id: {case['id']}.")
        seen.add(case["id"])
        started = time.perf_counter()
        ranked = list(search(case))
        latency_ms = (time.perf_counter() - started) * 1000
        if any(not isinstance(candidate_id, str) or not candidate_id for candidate_id in ranked):
            raise ValueError(f"Search returned an invalid candidate id for case {case['id']}.")
        metrics = evaluate_query(ranked, case["relevance"], ks)
        rows.append({"id": case["id"], "category": case["category"], "latency_ms": round(latency_ms, 2), "metrics": metrics})
        by_category.setdefault(case["category"], []).append(metrics)
        by_category_latency.setdefault(case["category"], []).append(latency_ms)
    if not rows:
        raise ValueError("Evaluation dataset contains no cases.")
    return {
        "query_count": len(rows),
        "queries": rows,
        "categories": {category: {**aggregate(metrics), **_latency_summary(by_category_latency[category])}
                       for category, metrics in sorted(by_category.items())},
        "aggregate": aggregate([row["metrics"] for row in rows]),
        "latency": _latency_summary([row["latency_ms"] for row in rows]),
    }


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"p50_ms": 0.0, "p95_ms": 0.0}
    p95_index = min(len(ordered) - 1, max(0, int((len(ordered) * 0.95 + 0.999999) - 1)))
    return {"p50_ms": round(median(ordered), 2), "p95_ms": round(ordered[p95_index], 2)}
