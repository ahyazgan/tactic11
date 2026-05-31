"""APIFootball degraded mode — kota aşımı / kaynak hatasında stale cache fallback.

Faz 9 #7: API-Football kotası bittiğinde 500 yerine son bilinen (bayatlamış)
yanıtla degraded çalışmaya devam eder.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.usage import QuotaExceeded
from app.data.cache import cache_set
from app.data.sources import api_football as af
from app.data.sources.api_football import APIFootball, _cache_key
from app.db import models


class _CtxSession:
    """SessionLocal() yerine test session'ını context-manager olarak verir."""

    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *a):
        return False


def _adapter() -> APIFootball:
    a = APIFootball.__new__(APIFootball)
    a._use_fixtures = False
    a._base_url = "https://example.test"
    a._key = "dummy-key"
    return a


def _expire(session, key: str) -> None:
    session.execute(
        models.CacheEntry.__table__.update()
        .where(models.CacheEntry.source == "api_football", models.CacheEntry.key == key)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    session.flush()


def test_quota_exceeded_returns_stale_cache(session, monkeypatch):
    monkeypatch.setattr(af, "SessionLocal", lambda: _CtxSession(session))

    key = _cache_key("teams", {"league": 203, "season": 2024})
    cache_set(session, source="api_football", key=key, value={"response": [1, 2]}, ttl_seconds=60)
    _expire(session, key)  # taze cache_get miss olsun
    session.commit()  # gerçekte önceki istekte commit'lenmiş olur (rollback'e dayanır)

    def _raise(*a, **k):
        raise QuotaExceeded("günlük kota aşıldı")

    monkeypatch.setattr(af, "consume_quota", _raise)

    out = _adapter()._http_get("teams", {"league": 203, "season": 2024})
    assert out == {"response": [1, 2]}  # stale değer döndü, exception yok


def test_quota_exceeded_without_cache_raises(session, monkeypatch):
    monkeypatch.setattr(af, "SessionLocal", lambda: _CtxSession(session))

    def _raise(*a, **k):
        raise QuotaExceeded("günlük kota aşıldı")

    monkeypatch.setattr(af, "consume_quota", _raise)

    with pytest.raises(QuotaExceeded):
        _adapter()._http_get("teams", {"league": 999, "season": 2024})


def test_http_failure_returns_stale_cache(session, monkeypatch):
    monkeypatch.setattr(af, "SessionLocal", lambda: _CtxSession(session))
    monkeypatch.setattr(af, "consume_quota", lambda *a, **k: None)

    key = _cache_key("fixtures", {"team": 611, "last": 10})
    cache_set(session, source="api_football", key=key, value={"response": ["m"]}, ttl_seconds=60)
    _expire(session, key)

    def _boom(*a, **k):
        raise httpx.ConnectError("kaynak düştü")

    monkeypatch.setattr(af, "call_with_retry", _boom)

    out = _adapter()._http_get("fixtures", {"team": 611, "last": 10})
    assert out == {"response": ["m"]}
