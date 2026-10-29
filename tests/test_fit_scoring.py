from types import SimpleNamespace

from backend.services.common.cache import clear_cache
from backend.services.llm import decision, fit_scoring, vllm
from backend.services.retrieval.search import parse_search_query


def _reply(monkeypatch, replies):
    calls = []

    def chat(messages, **kwargs):
        calls.append(messages)
        reply = replies[len(calls) - 1] if len(calls) <= len(replies) else replies[-1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(vllm, "chat_completion", chat)
    return calls


def test_score_fits_maps_one_to_five_onto_zero_to_one(monkeypatch):
    monkeypatch.setattr(fit_scoring.settings, "FIT_SCORE_WORKERS", 1)  # one worker keeps the replies in order
    _reply(monkeypatch, ["1", "3", "5", "Fit: 4"])
    assert fit_scoring.score_fits(["a", "b", "c", "d"]) == [0.0, 0.5, 1.0, 0.75]


def test_score_fits_ignores_replies_without_a_score(monkeypatch):
    _reply(monkeypatch, ["no idea"])
    assert fit_scoring.score_fits(["a"]) == [None]


def test_an_unreachable_model_stops_the_batch_after_the_first_failure(monkeypatch):
    monkeypatch.setattr(fit_scoring.settings, "FIT_SCORE_WORKERS", 1)
    calls = _reply(monkeypatch, [RuntimeError("Could not connect to DGX vLLM.")])
    assert fit_scoring.score_fits(["a", "b", "c"]) == [None, None, None]
    assert len(calls) == 1


def _item(score=60.0):
    cand = SimpleNamespace(file_hash="fit-test-hash", extracted_skills=["Java"], years_experience=5, education="BSc")
    pos = SimpleNamespace(id="fit-test-pos", jd_version=1, title="Java Dev", jd_text="Java developer")
    return score, cand, pos


def test_rerank_blends_the_fit_score_and_caches_it(monkeypatch):
    clear_cache("decision:")
    calls = _reply(monkeypatch, ["5"])
    weight = decision.settings.LAYA_RERANK_WEIGHT

    (blended, signal), = decision.rerank_scores_batch([_item(60.0)])
    assert signal == {"llm_fit_score": 100.0}
    assert blended == round((1 - weight) * 60.0 + weight * 100.0, 1)

    again, = decision.rerank_scores_batch([_item(60.0)])
    assert again == (blended, signal) and len(calls) == 1  # second time comes from the cache
    clear_cache("decision:")


def test_rerank_keeps_the_deterministic_score_when_the_model_is_down(monkeypatch):
    clear_cache("decision:")
    _reply(monkeypatch, [RuntimeError("down")])
    assert decision.rerank_scores_batch([_item(61.5)]) == [(61.5, None)]
    clear_cache("decision:")


def test_a_new_plain_query_does_not_inherit_the_previous_searchs_chips():
    skills, _, _, mode = parse_search_query("camunda bpmn", ["Java", "Spring"])
    assert mode == "neutral" and "Java" not in skills and "Spring" not in skills


def test_and_modifier_still_adds_to_the_active_chips():
    skills, _, _, mode = parse_search_query("camunda and bpmn", ["Java"])
    assert mode == "append" and "Java" in skills


def test_only_modifier_replaces_the_active_chips():
    skills, _, _, mode = parse_search_query("only Camunda", ["Java"])
    assert mode == "replace" and "Java" not in skills
