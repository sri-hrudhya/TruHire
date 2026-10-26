"""Regression: a search must not silently return zero candidates.

Root cause covered here: picking a JD pre-filled the hard Role filter from the requirement *title*
("... Job Description"), a token-subset match no candidate title can satisfy. Also: empty results now
say why (no candidates / no resume text / filters / skills / experience), and a missing OpenSearch
degrades to the supported vector/relational fallback with a visible warning.
"""
import pytest
from sqlalchemy import update

from backend.database import SessionLocal
from backend.models import Candidate, CandidateMatch
from backend.services.retrieval import filters as F
from backend.services.retrieval import search as search_module
from test_location_role_filters import env, retrieval, _ids, _search, _hits  # noqa: F401  (shared fixtures/helpers)


def test_search_returns_eligible_candidates_with_resume_text(env, retrieval):
    a, b = env["make"](), env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits(a, b), _hits(b, a)
    res = _search(env, query_text="python engineer")
    assert set(_ids(res)) == {a, b} and res["total_matches"] == 2
    assert res["empty_reason"] is None and res["warnings"] == []


def test_keyword_only_search_endpoint_needs_no_category_or_jd(env, retrieval):
    a = env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    r = env["client"].post("/api/search", headers=env["headers"], json={"query": "python"})
    assert r.status_code == 200 and a in _ids(r.json()) and r.json()["scored_against_jd"] is None


def test_jd_specific_search_uses_the_selected_jd(env, retrieval):
    a = env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    jd = env["make_jd"]()
    r = env["client"].post("/api/search", headers=env["headers"], json={"position_id": jd})
    body = r.json()
    assert r.status_code == 200 and body["scored_against_jd"]["id"] == jd and a in _ids(body)
    assert env["db"].query(CandidateMatch).filter_by(candidate_id=a, position_id=jd).count() == 1   # persisted as before
    assert env["client"].post("/api/search", headers=env["headers"], json={"position_id": "nope"}).status_code == 404


def test_jd_title_noise_is_not_a_role_requirement(env, monkeypatch):
    monkeypatch.setattr("backend.services.llm.ai_service.llm_extract_jd_filters", lambda t, x: None)
    assert F.strip_title_noise("Generative AI Solutions Architect Job Description") == "Generative AI Solutions Architect"
    assert F.strip_title_noise("Backend Engineer") == "Backend Engineer"
    out = F.extract_jd_filters("Senior Data Scientist Job Description", "We want someone great.")
    assert out["role"] == "Senior Data Scientist" and out["sources"]["role"] == "title"
    # The previous behaviour: the noise words became required tokens and matched nobody.
    assert not F.candidate_matches(None, ["Senior Data Scientist"], F.build_filters(None, "Senior Data Scientist Job Description"))
    assert F.candidate_matches(None, ["Data Scientist"], F.build_filters(None, out["role"]))


def test_filters_that_exclude_everyone_are_explained_not_generic(env, retrieval):
    a = env["make"](env["city"]("Pune"), ["Backend Engineer"])
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    res = _search(env, query_text="python", role="Generative AI Solutions Architect")
    assert res["results"] == [] and res["empty_reason"]["code"] == "filters_excluded_all"
    assert "Generative AI Solutions Architect" in res["empty_reason"]["message"]
    ok = _search(env, query_text="python", role="Backend Developer")           # same pool, valid filter -> not eliminated
    assert _ids(ok) == [a]


def test_skill_and_experience_exclusions_are_explained(env, retrieval):
    a = env["make"](skills=["Python"])
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    assert _search(env, query_text="x", filter_skills=["Rust"])["empty_reason"]["code"] == "skills_excluded_all"
    assert _search(env, query_text="x", min_experience=40)["empty_reason"]["code"] in {"experience_excluded_all", "no_retrieval_hits"}


def test_opensearch_unavailable_falls_back_and_warns(env, retrieval, monkeypatch):
    a = env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits(a), []
    monkeypatch.setattr(search_module, "get_opensearch_client", lambda: None)
    res = _search(env, query_text="python")
    assert _ids(res) == [a] and res["retrieval"]["lexical"] is False
    assert any("OpenSearch" in w for w in res["warnings"])

    retrieval["vector"] = []                                                    # both indexes empty -> relational pool
    res = _search(env, query_text="python")
    assert a in _ids(res) and res["warnings"]


def _reason(db, **kw):
    args = dict(filters=F.NO_FILTERS, active_skills=[], min_experience=None, pool_size=0, after_filters=0, after_skills=0, vector_rows=[], lexical_rows=[])
    args.update(kw)
    return search_module._empty_reason(db, **args)


def test_empty_database_and_missing_resume_text_have_actionable_messages(env):
    db = SessionLocal()
    try:
        db.execute(update(Candidate).values(resume_text=None))
        reason = _reason(db)
        assert reason["code"] == "no_resume_text" and "Re-ingest" in reason["message"]
        db.query(CandidateMatch).delete()
        db.query(Candidate).delete()
        reason = _reason(db)
        assert reason["code"] == "no_candidates" and "Ingestion" in reason["message"]
    finally:
        db.rollback()          # never persist: the isolated test DB keeps its seed data
        db.close()


def test_stale_cached_jd_filters_are_re_derived(env, monkeypatch):
    """Filters cached on a position before the fix (title noise as a role) must not be served again."""
    monkeypatch.setattr("backend.services.llm.ai_service.llm_extract_jd_filters", lambda t, x: None)
    jd = env["make_jd"]("We want someone great.", title="Data Scientist Job Description")
    from backend.models import Position
    pos = env["db"].query(Position).filter_by(id=jd).one()
    pos.search_filters = {"jd_version": pos.jd_version, "title": pos.title, "role": "Data Scientist Job Description", "location": None, "sources": {"role": "title"}}
    env["db"].commit()
    data = env["client"].get(f"/api/job-descriptions/{jd}/search-filters", headers=env["headers"]).json()
    assert "Description" not in (data["role"] or "")


def test_saved_role_and_location_are_not_restored_but_the_query_is(env, retrieval):
    """The reported bug: a stale 'New York' / 'Senior Data Scientist' filter came back on every page load."""
    a = env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    client, headers = env["client"], env["headers"]
    r = client.post("/api/search", headers=headers, json={"query": "python", "location": env["city"]("Atlantis"), "role": "Data Scientist"})
    assert r.status_code == 200
    state = client.get("/api/search/state", headers=headers).json()["state"]
    assert state["query"] == "python" and state["location"] is None and state["role"] is None


def test_filters_pushed_into_indexes_are_blamed_when_nothing_comes_back(env, retrieval):
    """Index push-down returns no hits for an unsatisfiable filter; the reason must name the filter, not the index."""
    env["make"]()
    retrieval["vector"], retrieval["lexical"] = [], []
    res = _search(env, query_text="camunda", location=env["city"]("New York"), role="Senior Data Scientist")
    assert res["results"] == [] and res["empty_reason"]["code"] == "filters_excluded_all"
    assert res["empty_reason"]["matches_without_filters"] >= 1
    clean = _search(env, query_text="camunda")                     # same data, no filters -> the relational pool answers
    assert clean["total_matches"] >= 1


def test_index_hits_for_deleted_candidates_fall_back_to_the_database(env, retrieval):
    a = env["make"]()
    retrieval["vector"], retrieval["lexical"] = _hits("deleted-1", "deleted-2"), _hits("deleted-1")
    res = _search(env, query_text="python")
    assert a in _ids(res)
