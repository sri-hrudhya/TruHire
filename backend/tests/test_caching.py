import time
from backend.services.cache import get_cache, set_cache, clear_cache


def test_cache_set_and_get():
    clear_cache()
    set_cache("test_key", {"data": 123}, ttl_seconds=60)
    cached = get_cache("test_key")
    assert cached == {"data": 123}


def test_cache_expiration():
    clear_cache()
    # Cache for 1 second
    set_cache("expiring_key", "temporary_value", ttl_seconds=1)
    assert get_cache("expiring_key") == "temporary_value"
    time.sleep(1.2)
    # Should be expired
    assert get_cache("expiring_key") is None


def test_cache_miss():
    clear_cache()
    assert get_cache("non_existent_key") is None
