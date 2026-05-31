from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data.cache import cache_get, cache_get_stale, cache_set
from app.db import models


def _expire(session, source: str, key: str) -> None:
    session.execute(
        models.CacheEntry.__table__.update()
        .where(models.CacheEntry.source == source, models.CacheEntry.key == key)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    session.flush()


def test_set_then_get_returns_value(session):
    cache_set(session, source="api_football", key="leagues?{}", value={"a": 1}, ttl_seconds=60)
    assert cache_get(session, source="api_football", key="leagues?{}") == {"a": 1}


def test_expired_entry_returns_none(session):
    cache_set(session, source="api_football", key="x", value={"v": 1}, ttl_seconds=60)
    # Süreyi geriye it
    session.execute(
        models.CacheEntry.__table__.update()
        .where(models.CacheEntry.source == "api_football", models.CacheEntry.key == "x")
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    session.flush()
    assert cache_get(session, source="api_football", key="x") is None


def test_set_overwrites_existing(session):
    cache_set(session, source="s", key="k", value={"v": 1}, ttl_seconds=60)
    cache_set(session, source="s", key="k", value={"v": 2}, ttl_seconds=60)
    assert cache_get(session, source="s", key="k") == {"v": 2}


def test_corrupted_value_returns_none_not_raises(session):
    cache_set(session, source="s", key="k", value={"ok": True}, ttl_seconds=60)
    # value sütununu doğrudan bozuk JSON'a çevir
    session.execute(
        models.CacheEntry.__table__.update()
        .where(models.CacheEntry.source == "s", models.CacheEntry.key == "k")
        .values(value="{not json")
    )
    session.flush()
    assert cache_get(session, source="s", key="k") is None


def test_stale_get_returns_expired_value(session):
    """cache_get None döner ama cache_get_stale süresi geçmiş değeri döner."""
    cache_set(session, source="api_football", key="k", value={"v": 9}, ttl_seconds=60)
    _expire(session, "api_football", "k")
    assert cache_get(session, source="api_football", key="k") is None
    assert cache_get_stale(session, source="api_football", key="k") == {"v": 9}


def test_stale_get_missing_returns_none(session):
    assert cache_get_stale(session, source="api_football", key="yok") is None


def test_stale_get_corrupted_returns_none(session):
    cache_set(session, source="s", key="k", value={"ok": True}, ttl_seconds=60)
    session.execute(
        models.CacheEntry.__table__.update()
        .where(models.CacheEntry.source == "s", models.CacheEntry.key == "k")
        .values(value="{not json")
    )
    session.flush()
    assert cache_get_stale(session, source="s", key="k") is None
