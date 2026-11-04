import uuid

from backend.models import ROLE_ADMIN, ROLE_RECRUITER, Candidate
from test_location_role_filters import env  # noqa: F401  (shared fixture)
from test_roles import users  # noqa: F401  (user factory)


def _candidate(db, uploader_id, tag, label):
    c = Candidate(display_id=f"UF-{tag}-{label}", candidate_name=f"{label} {tag}", resume_text="x", status="New", uploaded_by=uploader_id,
                  file_hash=uuid.uuid4().hex, original_filename=f"{label}.txt", extracted_skills=[])
    db.add(c)
    db.commit()
    return c.id


def _names(env, headers, **params):
    body = env["client"].get("/api/candidates", headers=headers, params={"limit": 100, "q": params.pop("tag"), **params}).json()
    return {c["candidate_name"].split()[0] for c in body["candidates"]}, body


def test_uploaded_by_filter_is_per_user_and_admin_only_for_others(env, users):
    db, tag = env["db"], uuid.uuid4().hex[:8]
    a, ha = users(ROLE_RECRUITER)
    b, hb = users(ROLE_RECRUITER)
    admin, hadmin = users(ROLE_ADMIN)
    ids = [_candidate(db, a.id, tag, "A"), _candidate(db, b.id, tag, "B")]
    try:
        # No param: unchanged behaviour (everything), used by search/review callers.
        assert _names(env, ha, tag=tag)[0] == {"A", "B"}
        # Recruiter: 'me', someone else's id and 'all' all collapse to their own resumes.
        for value in ("me", b.id, "all"):
            assert _names(env, ha, tag=tag, uploaded_by=value)[0] == {"A"}
        # Cache must not leak between users for the same query.
        assert _names(env, hb, tag=tag, uploaded_by="me")[0] == {"B"}
        # Admin: 'me' is their own (none), a specific id, and 'all'.
        assert _names(env, hadmin, tag=tag, uploaded_by="me")[0] == set()
        assert _names(env, hadmin, tag=tag, uploaded_by=b.id)[0] == {"B"}
        names, body = _names(env, hadmin, tag=tag, uploaded_by="all")
        assert names == {"A", "B"}
        assert {c["uploaded_by_name"] for c in body["candidates"]} == {a.name, b.name}
    finally:
        db.query(Candidate).filter(Candidate.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
