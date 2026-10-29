"""Category + keyword search: `demand_id` scopes a requirement-less search to one category."""
import pytest

from backend.models import canonical_demand_id
from backend.services.classification import matches_category
from test_location_role_filters import env, retrieval, _ids, _hits  # noqa: F401  (shared fixtures/helpers)

CAMUNDA = ["Camunda", "BPMN"]
JAVA = ["Java", "Spring Boot", "Hibernate"]


def _post(env, **body):
    return env["client"].post("/api/search", headers=env["headers"], json=body)


def test_matches_category_allows_more_than_one_category():
    assert matches_category("Camunda", ["Process Engineer"], CAMUNDA + ["Java"], "")
    assert matches_category("Java", [], CAMUNDA + JAVA, "")
    assert not matches_category("Pega", [], JAVA, "java services")
    assert matches_category("Others", [], ["Excel"], "accounting")
    assert not matches_category("Others", [], CAMUNDA, "")


def test_category_plus_keyword_restricts_to_category(env, retrieval):
    camunda, java = env["make"](skills=CAMUNDA), env["make"](skills=JAVA)
    retrieval["vector"], retrieval["lexical"] = _hits(camunda, java), _hits(java, camunda)
    r = _post(env, query="engineer", demand_id=canonical_demand_id("Camunda"))
    assert r.status_code == 200
    assert _ids(r.json()) == [camunda] and r.json()["scored_against_jd"] is None


def test_category_without_query_or_jd_rejected_422(env, retrieval):
    r = _post(env, demand_id=canonical_demand_id("Java"))
    assert r.status_code == 422 and "Java" in r.json()["detail"]


def test_category_with_matching_jd_is_allowed_and_mismatched_jd_is_422(env, retrieval):
    a = env["make"](skills=CAMUNDA)
    retrieval["vector"], retrieval["lexical"] = _hits(a), _hits(a)
    jd = env["make_jd"](text="Camunda BPMN workflow engineer building Camunda process automation.", title="Camunda Engineer")
    assert _post(env, position_id=jd, demand_id=canonical_demand_id("Camunda")).status_code == 200
    r = _post(env, position_id=jd, demand_id=canonical_demand_id("Pega"))
    assert r.status_code == 422 and "Pega" in r.json()["detail"]


def test_unknown_category_404(env, retrieval):
    assert _post(env, query="java", demand_id="does-not-exist").status_code == 404


def test_category_with_no_matching_candidates_explains_empty(env, retrieval):
    java = env["make"](skills=JAVA)
    retrieval["vector"], retrieval["lexical"] = _hits(java), _hits(java)
    r = _post(env, query="engineer", demand_id=canonical_demand_id("Pega"))
    body = r.json()
    assert r.status_code == 200 and body["results"] == []
    assert body["empty_reason"]["code"] == "category_excluded_all" and "Pega" in body["empty_reason"]["message"]


def test_cache_does_not_leak_between_categories(env, retrieval):
    camunda, java = env["make"](skills=CAMUNDA), env["make"](skills=JAVA)
    retrieval["vector"], retrieval["lexical"] = _hits(camunda, java), _hits(camunda, java)
    in_camunda = _ids(_post(env, query="engineer", demand_id=canonical_demand_id("Camunda")).json())
    in_java = _ids(_post(env, query="engineer", demand_id=canonical_demand_id("Java")).json())
    assert in_camunda == [camunda] and java in in_java
