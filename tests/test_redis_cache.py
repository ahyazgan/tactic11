"""Redis cache backend (Faz 9 #9) — envelope TTL, stale, DB fallback."""

from __future__ import annotations

import pytest

from app.data.cache import cache_get, cache_get_stale, cache_set
from app.data.cache import redis_backend as rb


class FakeRedis:
    """Minimal in-memory Redis taklidi (get/setex/ping)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def ping(self):
        return True


@pytest.fixture()
def fake_redis():
    client = FakeRedis()
    rb.set_redis_client_for_test(client)
    try:
        yield client
    finally:
        rb.reset_redis_client()  # diğer testlere sızmasın (modül global)


def test_set_then_get_via_redis(session, fake_redis):
    cache_set(session, source="api_football", key="k", value={"a": 1}, ttl_seconds=60)
    # Redis'e yazıldı, DB'ye değil
    assert any("api_football" in k for k in fake_redis.store)
    assert cache_get(session, source="api_football", key="k") == {"a": 1}


def test_expired_logical_ttl_returns_none_but_stale_returns_value(session, fake_redis):
    cache_set(session, source="api_football", key="k", value={"v": 9}, ttl_seconds=0)
    # ttl=0 → mantıksal exp = now → cache_get expired sayar
    assert cache_get(session, source="api_football", key="k") is None
    # stale Redis'te hâlâ duruyor (retention uzun)
    assert cache_get_stale(session, source="api_football", key="k") == {"v": 9}


def test_redis_miss_returns_none(session, fake_redis):
    assert cache_get(session, source="api_football", key="yok") is None
    assert cache_get_stale(session, source="api_football", key="yok") is None


def test_redis_error_falls_back_to_db(session):
    class BrokenRedis:
        def get(self, key):
            raise RuntimeError("redis down")

        def setex(self, key, ttl, value):
            raise RuntimeError("redis down")

    rb.set_redis_client_for_test(BrokenRedis())
    try:
        # set Redis'te patlar → DB'ye yazılır; get de DB'den okur
        cache_set(session, source="s", key="k", value={"db": True}, ttl_seconds=60)
        assert cache_get(session, source="s", key="k") == {"db": True}
    finally:
        rb.reset_redis_client()


def test_no_redis_uses_db(session):
    """REDIS_URL boş (test default) → DB path; mevcut davranış korunur."""
    rb.reset_redis_client()
    cache_set(session, source="s", key="k2", value={"db": 1}, ttl_seconds=60)
    assert cache_get(session, source="s", key="k2") == {"db": 1}


def test_envelope_roundtrip_unit():
    client = FakeRedis()
    rb.redis_set(client, source="x", key="y", value={"n": 5}, ttl_seconds=100)
    assert rb.redis_get(client, source="x", key="y") == {"n": 5}
    assert rb.redis_get_stale(client, source="x", key="y") == {"n": 5}
