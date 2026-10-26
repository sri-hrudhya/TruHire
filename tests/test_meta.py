from backend.config import settings
from backend.models import CANDIDATE_STATUSES, REQUIREMENT_STATUSES
from test_location_role_filters import env  # noqa: F401  (shared fixture)


def test_meta_returns_enums_from_models(env):
    r = env["client"].get("/api/meta", headers=env["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["requirement_statuses"] == list(REQUIREMENT_STATUSES)
    assert body["search"]["max_top_n"] == settings.SEARCH_MAX_TOP_N
    assert body["comment_max_chars"] == settings.COMMENT_MAX_CHARS
    assert body["roles"] == ["admin", "recruiter"]
    assert body["candidate_statuses"] == list(CANDIDATE_STATUSES)


def test_meta_requires_auth(env):
    assert env["client"].get("/api/meta").status_code == 401
