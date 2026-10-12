import math

from backend.evaluation.metrics import aggregate, evaluate_query, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from backend.services.ingestion.chunking import chunk_text, profile_chunks
from backend.services.retrieval.reranker import blend


def test_precision_recall_mrr():
    rel = {"a": 1, "c": 1, "z": 1}
    ranked = ["a", "b", "c", "d"]
    assert precision_at_k(ranked, rel, 2) == 0.5
    assert math.isclose(recall_at_k(ranked, rel, 4), 2 / 3)
    assert reciprocal_rank(["x", "b", "c"], rel) == 1 / 3
    assert reciprocal_rank(["x"], rel) == 0.0


def test_ndcg_perfect_and_worst_order():
    rel = {"a": 2, "b": 1}
    assert math.isclose(ndcg_at_k(["a", "b", "x"], rel, 3), 1.0)
    assert ndcg_at_k(["x", "y", "z"], rel, 3) == 0.0
    assert ndcg_at_k(["b", "a"], rel, 2) < 1.0
    assert ndcg_at_k(["a"], {}, 3) == 0.0  # no relevant docs: defined as 0, never a division error


def test_evaluate_and_aggregate():
    q1 = evaluate_query(["a", "b"], {"a": 1}, [1, 2])
    q2 = evaluate_query(["b", "a"], {"a": 1}, [1, 2])
    agg = aggregate([q1, q2])
    assert q1["precision@1"] == 1.0 and q2["precision@1"] == 0.0
    assert agg["precision@1"] == 0.5 and agg["mrr"] == 0.75


def test_chunking_covers_whole_resume_with_overlap():
    text = " ".join(f"word{i}" for i in range(3000))  # ~20K chars, far beyond one embedding window
    chunks = chunk_text(text, size=1400, overlap=200, max_chunks=50)
    assert len(chunks) > 10 and all(len(c) <= 1400 for c in chunks)
    assert chunks[0].startswith("word0") and "word2999" in chunks[-1]
    # Consecutive chunks overlap so a sentence on a boundary is never lost.
    assert set(chunks[0].split()[-10:]) & set(chunks[1].split()[:60])
    assert all(c.startswith("Name: X") for c in profile_chunks("Name: X", text))
    assert chunk_text("") == [] and chunk_text("short") == ["short"]


def test_reranker_blend_is_bounded_and_monotonic():
    assert blend(80.0, 1.0) > blend(80.0, 0.0)
    assert 0.0 <= blend(0.0, 0.0) and blend(100.0, 1.0) <= 100.0


def test_skill_matching_normalizes_and_falls_back_to_resume_text():
    from backend.services.retrieval.scoring import compute_skill_overlap, normalize_skill
    assert normalize_skill("Camunda 8.5") == "camunda" and normalize_skill("REST APIs") == "rest api" and normalize_skill("NodeJS") == "node.js"
    # parsed skills lack Camunda/BPMN, but the resume text has them: still counts as a match
    cov, matched, missing = compute_skill_overlap(["Java 17"], ["Java", "Camunda", "BPMN", "Rust"], "Built Camunda 8 flows modelled in BPMN 2.0")
    assert (cov, missing) == (0.75, ["Rust"]) and set(matched) == {"Java", "Camunda", "BPMN"}


def test_truncated_llm_json_is_salvaged_not_discarded():
    from backend.services.llm.ai_service import _json_from_response
    cut = '{"candidate_name": "A B", "extracted_skills": ["Java", "Camunda", "Mav'  # model hit its token limit mid-list
    assert _json_from_response(cut) == {"candidate_name": "A B", "extracted_skills": ["Java", "Camunda"]}
