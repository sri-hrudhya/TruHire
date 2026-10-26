import uuid

import pytest

from backend.auth import create_access_token, get_password_hash
from backend.config import settings
from backend.models import ROLE_ADMIN, ROLE_RECRUITER, User
from test_location_role_filters import env  # noqa: F401  (shared fixture)


@pytest.fixture
def users(env):
    """Factory for throwaway users; removed afterwards."""
    db, made = env["db"], []

    def make(role):
        u = User(email=f"{role}.{uuid.uuid4().hex[:8]}@truhire.test", name=f"{role} user",
                 hashed_password=get_password_hash("pass12345"), role=role)
        db.add(u)
        db.commit()
        made.append(u.id)
        return u, {"Authorization": f"Bearer {create_access_token({'sub': u.id})}"}

    yield make
    db.rollback()
    db.query(User).filter(User.id.in_(made)).delete(synchronize_session=False)
    db.commit()


def _register(env, email):
    return env["client"].post("/api/auth/register", json={"email": email, "name": "New Person", "password": "pass12345"})


def _forget(env, email):
    env["db"].query(User).filter(User.email == email).delete()
    env["db"].commit()


def test_register_defaults_to_recruiter(env):
    email = f"plain.{uuid.uuid4().hex[:8]}@truhire.test"
    r = _register(env, email)
    assert r.status_code == 200 and r.json()["user"]["role"] == ROLE_RECRUITER
    _forget(env, email)


def test_bootstrap_admin_email_gets_admin(env, monkeypatch):
    email = f"boss.{uuid.uuid4().hex[:8]}@truhire.test"
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAILS", f"someone@else.com, {email.upper()}")
    r = _register(env, email)
    assert r.status_code == 200 and r.json()["user"]["role"] == ROLE_ADMIN
    _forget(env, email)


def test_users_list_forbidden_for_recruiter(env, users):
    _, headers = users(ROLE_RECRUITER)
    assert env["client"].get("/api/users", headers=headers).status_code == 403


def test_admin_lists_users_and_changes_role(env, users):
    _, admin_headers = users(ROLE_ADMIN)
    target, _ = users(ROLE_RECRUITER)
    assert env["client"].get("/api/users", headers=admin_headers).status_code == 200
    r = env["client"].patch(f"/api/users/{target.id}/role", headers=admin_headers, json={"role": ROLE_ADMIN})
    assert r.status_code == 200 and r.json()["role"] == ROLE_ADMIN
    assert env["client"].patch(f"/api/users/{target.id}/role", headers=admin_headers,
                               json={"role": "root"}).status_code == 422


def test_cannot_demote_last_admin(env, users):
    db = env["db"]
    admin, headers = users(ROLE_ADMIN)
    # Make this the only admin for the duration of the check.
    others = db.query(User).filter(User.role == ROLE_ADMIN, User.id != admin.id).all()
    previous = [(u, u.role) for u in others]
    for u in others:
        u.role = ROLE_RECRUITER
    db.commit()
    try:
        r = env["client"].patch(f"/api/users/{admin.id}/role", headers=headers, json={"role": ROLE_RECRUITER})
        assert r.status_code == 409
    finally:
        for u, role in previous:
            u.role = role
        db.commit()


def test_me_reports_a_role_even_for_pre_roles_users(env):
    user = env["db"].query(User).filter(User.id == env["user"].id).first()
    user.role = None
    env["db"].commit()
    r = env["client"].get("/api/auth/me", headers=env["headers"])
    assert r.status_code == 200 and r.json()["role"] == ROLE_RECRUITER
