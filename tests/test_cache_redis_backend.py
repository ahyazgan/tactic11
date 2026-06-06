"""Redis cache backend — graceful disabled yolu + RedisCache get/set (fake)."""
from __future__ import annotations

from app.data.cache import redis_backend
from app.data.cache.redis_backend import RedisCache, _redis_key, get_redis_cache


def test_redis_key_namespacing() -> None:
    assert _redis_key("api_football", "team:42") == "m2:api_football:team:42"


def test_get_redis_cache_disabled_when_no_url(monkeypatch) -> None:
    # redis_url boş → backend None (DB cache'e düşülür)
    redis_backend.reset_redis_cache()

    class _S:
        redis_url = ""

    monkeypatch.setattr(redis_backend, "REDIS_AVAILABLE", True)
    monkeypatch.setattr(
        "app.core.config.get_settings", lambda: _S(), raising=True,
    )
    assert get_redis_cache() is None
    redis_backend.reset_redis_cache()


def test_get_redis_cache_disabled_when_lib_missing(monkeypatch) -> None:
    redis_backend.reset_redis_cache()
    monkeypatch.setattr(redis_backend, "REDIS_AVAILABLE", False)
    assert get_redis_cache() is None
    redis_backend.reset_redis_cache()


class _FakeClient:
    """Minimal in-memory redis taklidi — get/setex."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, k: str) -> str | None:
        return self.store.get(k)

    def setex(self, k: str, ttl: int, v: str) -> None:
        self.store[k] = v


def test_rediscache_roundtrip() -> None:
    c = RedisCache(_FakeClient())
    assert c.get("src", "k") is None
    assert c.set("src", "k", {"a": 1}, 60) is True
    assert c.get("src", "k") == {"a": 1}


def test_rediscache_get_swallows_backend_error() -> None:
    class _Boom:
        def get(self, k: str):
            raise RuntimeError("conn lost")

    # Hata yutulur → None (çağıran DB cache'e düşer)
    assert RedisCache(_Boom()).get("s", "k") is None


def test_rediscache_set_swallows_backend_error() -> None:
    class _Boom:
        def setex(self, k, ttl, v):
            raise RuntimeError("conn lost")

    assert RedisCache(_Boom()).set("s", "k", {"x": 1}, 30) is False
