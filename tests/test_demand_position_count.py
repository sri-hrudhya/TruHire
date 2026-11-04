import uuid

from fastapi.testclient import TestClient

from backend.auth import create_access_token
from backend.database import SessionLocal
from backend.main import app
from backend.models import Position, User, canonical_demand_id

client = TestClient(app)


def _practice(headers, name="Others"):
    return next(d for d in client.get("/api/demands", headers=headers).json() if d["name"] == name)


def test_practice_position_count_sums_positions_of_live_demands_only():
    db = SessionLocal()
    user = db.query(User).first()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    before = _practice(headers)
    tag = uuid.uuid4().hex[:8]
    rows = [(3, "Open"), (2, None), (5, "Cancelled"), (None, "Open"), (0, "Open"), (4, "Fulfilled")]
    made = [Position(title=f"PC {tag} {i}", jd_text="x", created_by=user.id, demand_id=canonical_demand_id("Others"), no_of_positions=n, status=s)
            for i, (n, s) in enumerate(rows)]
    try:
        db.add_all(made)
        db.commit()
        after = _practice(headers)
        assert after["position_count"] - before["position_count"] == 3 + 2 + 4  # cancelled, blank and zero add nothing
        assert after["jd_count"] - before["jd_count"] == 5  # every live demand, cancelled left out
    finally:
        db.query(Position).filter(Position.id.in_([p.id for p in made])).delete(synchronize_session=False)
        db.commit()
        db.close()
