import pytest

from backend.evaluation.runner import evaluate_cases, load_cases


def test_evaluate_cases_reports_metrics_by_query_and_category():
    cases = [{
        "id": "q1",
        "category": "client",
        "query": "Python engineer for Acme",
        "relevance": {"candidate-a": 2, "candidate-b": 1},
    }]

    report = evaluate_cases(cases, lambda case: ["candidate-a", "candidate-x"])

    assert report["queries"][0]["id"] == "q1"
    assert report["queries"][0]["metrics"]["ndcg@10"] == pytest.approx(0.8262, abs=1e-4)
    assert report["categories"]["client"]["recall@50"] == 0.5
    assert report["aggregate"]["mrr"] == 1.0


def test_load_cases_rejects_resume_text_and_invalid_relevance(tmp_path):
    dataset = tmp_path / "private.jsonl"
    dataset.write_text('{"id":"q1","query":"python","resume_text":"private","relevance":{"a":5}}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="resume_text"):
        load_cases(dataset)
