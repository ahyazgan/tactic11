"""app.api.live_feed_factory + dürüst sağlayıcı durumu testleri.

WS handler'ın somut feed'den ayrılması (fabrika): config'ten kaynak seçilir,
kayıtlı adapter'ı olmayan mod güvenle replay'e düşer, mevcut WS davranışı
(maç yoksa ValueError) korunur.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.api.live_feed_factory import build_live_feed, resolve_feed_mode
from app.api.live_provider import build_provider_status
from app.api.replay_feed import StatsBombReplayFeed
from app.core.config import Settings
from app.db import models
from app.sports import football


def _seed_match(session, match_id: int = 8800):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    session.commit()


def _settings(mode: str) -> Settings:
    return Settings(LIVE_FEED_MODE=mode)


# ── resolve_feed_mode ────────────────────────────────────────────────────────

def test_resolve_default_is_replay():
    assert resolve_feed_mode(_settings("replay")) == "replay"


def test_resolve_unknown_mode_falls_back_to_replay():
    # Koordinatlı adapter henüz yok → live_api seçilse bile replay.
    assert resolve_feed_mode(_settings("live_api")) == "replay"
    assert resolve_feed_mode(_settings("garbage")) == "replay"


# ── build_live_feed ──────────────────────────────────────────────────────────

def test_build_live_feed_returns_replay_feed(session):
    _seed_match(session)
    feed = build_live_feed(session, 8800)
    assert isinstance(feed, StatsBombReplayFeed)
    assert feed.mode() == "replay_statsbomb"
    assert feed.home_team_id == 11 and feed.away_team_id == 22


def test_build_live_feed_missing_match_raises(session):
    # WS handler bunu yakalayıp istemciye 'error' iletir (mevcut davranış).
    with pytest.raises(ValueError):
        build_live_feed(session, 999999)


def test_build_live_feed_live_api_mode_still_replay(session):
    _seed_match(session, match_id=8801)
    feed = build_live_feed(session, 8801, settings=_settings("live_api"))
    assert isinstance(feed, StatsBombReplayFeed)  # güvenli fallback


# ── dürüst sağlayıcı durumu ─────────────────────────────────────────────────

def test_provider_status_replay_source_is_honest():
    st = build_provider_status(source="replay_statsbomb")
    assert st["status"] == "replay"
    assert st["source"] == "replay_statsbomb"
    assert st["is_demo_key"] is True          # config'te gerçek key yok
    assert "••" in str(st["api_key_masked"])  # tam key sızmaz


def test_provider_status_live_source_marks_connected():
    st = build_provider_status(source="live_opta")
    assert st["status"] == "connected"
    assert st["source"] == "live_opta"


def test_provider_status_real_key_not_demo():
    s = Settings(LIVE_FEED_API_KEY="real_secret_key_123456")
    st = build_provider_status(s, source="replay_statsbomb")
    assert st["is_demo_key"] is False
