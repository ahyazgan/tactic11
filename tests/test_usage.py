from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.usage import QuotaExceeded, guard_quota, record_call
from app.db import models


def test_record_appends_event(session):
    record_call(session, source="api_football", endpoint="leagues")
    record_call(session, source="api_football", endpoint="teams")
    n = session.scalar(select(func.count()).select_from(models.UsageEvent))
    assert n == 2


def test_guard_raises_when_daily_limit_hit(session, monkeypatch):
    fake = Settings(
        API_FOOTBALL_DAILY_LIMIT=2,
        API_FOOTBALL_MONTHLY_LIMIT=100,
        ANTHROPIC_DAILY_TOKEN_LIMIT=100,
    )
    monkeypatch.setattr("app.core.usage.tracker.get_settings", lambda: fake)

    record_call(session, source="api_football", endpoint="leagues")
    record_call(session, source="api_football", endpoint="teams")
    with pytest.raises(QuotaExceeded):
        guard_quota(session, "api_football")


def test_guard_anthropic_tokens(session, monkeypatch):
    fake = Settings(
        API_FOOTBALL_DAILY_LIMIT=10_000,
        API_FOOTBALL_MONTHLY_LIMIT=100_000,
        ANTHROPIC_DAILY_TOKEN_LIMIT=100,
    )
    monkeypatch.setattr("app.core.usage.tracker.get_settings", lambda: fake)

    record_call(session, source="anthropic", endpoint="messages", tokens=60)
    guard_quota(session, "anthropic")  # 60 < 100, geçer
    record_call(session, source="anthropic", endpoint="messages", tokens=50)
    with pytest.raises(QuotaExceeded):
        guard_quota(session, "anthropic")


def test_unknown_source_no_raise(session):
    # Tanımsız source için sessiz geçer — get_settings cache'i temizle
    get_settings.cache_clear()
    guard_quota(session, "made_up")


def test_consume_quota_atomic_guard_then_record(session, monkeypatch):
    """consume_quota tek transaction'da guard+record yapar; limit semantiği
    eski guard_quota ile aynı (limit=N → N başarılı, N+1.de raise)."""
    from app.core.usage import consume_quota

    fake = Settings(API_FOOTBALL_DAILY_LIMIT=2, API_FOOTBALL_MONTHLY_LIMIT=100, ANTHROPIC_DAILY_TOKEN_LIMIT=100)
    monkeypatch.setattr("app.core.usage.tracker.get_settings", lambda: fake)

    consume_quota(session, source="api_football", endpoint="leagues")
    consume_quota(session, source="api_football", endpoint="teams")
    n = session.scalar(select(func.count()).select_from(models.UsageEvent))
    assert n == 2

    # 3. çağrıda raise — kayıt eklenmemeli (guard önce çağrılıyor)
    with pytest.raises(QuotaExceeded):
        consume_quota(session, source="api_football", endpoint="fixtures")
    n2 = session.scalar(select(func.count()).select_from(models.UsageEvent))
    assert n2 == 2
