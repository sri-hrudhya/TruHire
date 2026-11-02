"""Behaviour that keeps the API responsive for many users and several workers."""
import asyncio

from starlette.requests import Request

from backend.auth import create_access_token
from backend.rate_limit import client_key
from backend.services.common import retention


def _request(token=None, ip="10.0.0.5"):
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "headers": headers, "client": (ip, 1234), "method": "GET", "path": "/"})


def test_rate_limit_is_counted_per_user_not_per_proxy_ip():
    a, b = create_access_token({"sub": "user-a"}), create_access_token({"sub": "user-b"})
    # Both arrive from the same nginx address, yet get separate budgets.
    assert client_key(_request(a)) == "user:user-a"
    assert client_key(_request(b)) == "user:user-b"


def test_signed_out_and_bad_tokens_are_counted_by_ip():
    assert client_key(_request(None, ip="203.0.113.7")) == "203.0.113.7"
    assert client_key(_request("not-a-token", ip="203.0.113.8")) == "203.0.113.8"


class _FakeRedis:
    def __init__(self):
        self.taken = False

    def set(self, key, value, nx=False, ex=None):
        if nx and self.taken:
            return None
        self.taken = True
        return True


def test_only_one_worker_claims_each_retention_cycle(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(retention, "get_redis_client", lambda: fake)
    assert retention._claim_cleanup_cycle(24) is True
    assert retention._claim_cleanup_cycle(24) is False  # a second worker in the same cycle skips it


def test_cleanup_claim_works_without_redis(monkeypatch):
    monkeypatch.setattr(retention, "get_redis_client", lambda: None)
    assert retention._claim_cleanup_cycle(24) is True


def test_retention_cleanup_runs_off_the_event_loop(monkeypatch):
    """The blocking cleanup must not run on the loop thread, or every request stalls while it works."""
    import threading
    seen = {}
    monkeypatch.setattr(retention.settings, "RETENTION_CLEANUP_INTERVAL_HOURS", 1)
    monkeypatch.setattr(retention, "get_redis_client", lambda: None)

    def fake_cleanup():
        seen["thread"] = threading.current_thread()
        raise asyncio.CancelledError  # stop the endless loop after the first cycle

    monkeypatch.setattr(retention, "run_retention_cleanup", fake_cleanup)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(retention.asyncio, "sleep", lambda s: real_sleep(0))

    async def go():
        main_thread = threading.current_thread()
        try:
            await retention.schedule_retention_cleanup_task()
        except asyncio.CancelledError:
            pass
        return main_thread

    main_thread = asyncio.run(go())
    assert seen["thread"] is not main_thread
