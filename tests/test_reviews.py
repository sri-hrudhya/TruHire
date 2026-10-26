import pytest

from backend.config import settings
from backend.models import ROLE_ADMIN, ROLE_RECRUITER, CandidateAssignment, CandidateComment
from test_location_role_filters import env  # noqa: F401  (shared fixture)
from test_roles import users  # noqa: F401  (user factory)


@pytest.fixture
def scene(env, users):
    """A candidate, a requirement, an admin and two recruiters."""
    admin, admin_h = users(ROLE_ADMIN)
    rec_a, a_h = users(ROLE_RECRUITER)
    rec_b, b_h = users(ROLE_RECRUITER)
    cid, pid = env["make"](), env["make_jd"]()
    return {"cid": cid, "pid": pid, "admin": (admin, admin_h), "a": (rec_a, a_h), "b": (rec_b, b_h), "env": env}


def _assign(scene, headers, assignee_id):
    return scene["env"]["client"].put(
        f"/api/job-descriptions/{scene['pid']}/candidates/{scene['cid']}/assignment", headers=headers,
        json={"assignee_id": assignee_id})


def test_admin_assigns_candidate(scene):
    _, h = scene["admin"]
    rec, _ = scene["a"]
    r = _assign(scene, h, rec.id)
    assert r.status_code == 200 and r.json()["assignee"]["id"] == rec.id
    listed = scene["env"]["client"].get(f"/api/job-descriptions/{scene['pid']}/assignments", headers=h).json()
    assert [a["candidate_id"] for a in listed] == [scene["cid"]]


def test_recruiter_cannot_assign_others(scene):
    rec_a, a_h = scene["a"]
    rec_b, _ = scene["b"]
    assert _assign(scene, a_h, rec_b.id).status_code == 403
    assert _assign(scene, a_h, rec_a.id).status_code == 200  # claiming for yourself is fine


def test_recruiter_cannot_take_over_a_candidate_assigned_to_someone_else(scene):
    _, admin_h = scene["admin"]
    rec_a, _ = scene["a"]
    rec_b, b_h = scene["b"]
    assert _assign(scene, admin_h, rec_a.id).status_code == 200
    assert _assign(scene, b_h, rec_b.id).status_code == 403


def test_mine_filter_lists_only_my_assignments(scene):
    _, admin_h = scene["admin"]
    rec_a, a_h = scene["a"]
    _assign(scene, admin_h, rec_a.id)
    client, pid = scene["env"]["client"], scene["pid"]
    assert len(client.get(f"/api/job-descriptions/{pid}/assignments?mine=true", headers=a_h).json()) == 1
    _, b_h = scene["b"]
    assert client.get(f"/api/job-descriptions/{pid}/assignments?mine=true", headers=b_h).json() == []


def test_comment_roundtrip_with_rating(scene):
    env = scene["env"]
    rec_a, a_h = scene["a"]
    r = env["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h,
                           json={"body": "  Strong on Camunda  ", "rating": 4, "position_id": scene["pid"]})
    assert r.status_code == 200
    c = r.json()
    assert c["body"] == "Strong on Camunda" and c["rating"] == 4 and c["author"]["id"] == rec_a.id and c["can_edit"]
    _, b_h = scene["b"]
    seen = env["client"].get(f"/api/candidates/{scene['cid']}/comments", headers=b_h).json()
    assert [x["id"] for x in seen] == [c["id"]] and seen[0]["can_edit"] is False  # shared, but read-only for others


@pytest.mark.parametrize("body", ["", "   \n\t"])
def test_empty_comment_422(scene, body):
    _, a_h = scene["a"]
    r = scene["env"]["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h, json={"body": body})
    assert r.status_code == 422


def test_comment_over_max_chars_422(scene):
    _, a_h = scene["a"]
    r = scene["env"]["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h,
                                    json={"body": "x" * (settings.COMMENT_MAX_CHARS + 1)})
    assert r.status_code == 422


def test_rating_out_of_range_422(scene):
    _, a_h = scene["a"]
    r = scene["env"]["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h,
                                    json={"body": "ok", "rating": 6})
    assert r.status_code == 422


def test_only_author_or_admin_edits_comment(scene):
    env = scene["env"]
    _, a_h = scene["a"]
    _, b_h = scene["b"]
    _, admin_h = scene["admin"]
    cid = env["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h, json={"body": "mine"}).json()["id"]
    assert env["client"].patch(f"/api/comments/{cid}", headers=b_h, json={"body": "hijack"}).status_code == 403
    assert env["client"].delete(f"/api/comments/{cid}", headers=b_h).status_code == 403
    r = env["client"].patch(f"/api/comments/{cid}", headers=a_h, json={"body": "edited"})
    assert r.status_code == 200 and r.json()["body"] == "edited" and r.json()["edited_at"]
    assert env["client"].delete(f"/api/comments/{cid}", headers=admin_h).status_code == 200


def test_deleting_candidate_removes_comments_and_assignments(scene):
    env = scene["env"]
    _, admin_h = scene["admin"]
    rec, a_h = scene["a"]
    _assign(scene, admin_h, rec.id)
    env["client"].post(f"/api/candidates/{scene['cid']}/comments", headers=a_h, json={"body": "gone soon"})
    assert env["client"].delete(f"/api/candidates/{scene['cid']}", headers=env["headers"]).status_code in (200, 204)
    db = env["db"]
    db.expire_all()
    assert db.query(CandidateAssignment).filter_by(candidate_id=scene["cid"]).count() == 0
    assert db.query(CandidateComment).filter_by(candidate_id=scene["cid"]).count() == 0
