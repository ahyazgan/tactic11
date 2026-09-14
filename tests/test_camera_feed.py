"""CameraLiveFeed — takip hattından canlı feed: saat = son kare, gecikme ölçülür.

Kilitlenen davranış: kare yokken saat 0 ve gecikme None; kare gelince saat son
karenin dakikası, gecikme = şimdi − created_at; `refresh` DB'ye eklenen pas
olaylarını pencereye alır; fabrika `mode="camera"` ile bu feed'i kurar.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.api.camera_feed import CAMERA_MODE, CameraLiveFeed
from app.api.live_feed_factory import build_live_feed
from app.db import models
from app.sports import football

MATCH, HOME, AWAY = 990777, 9001, 9002


def _seed_match(session) -> None:
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-cam", slug="t-cam", name="t-cam", settings_json="{}",
                              active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=MATCH, league_external_id=999, season=2026,
        kickoff=now, status="LIVE", home_team_external_id=HOME, away_team_external_id=AWAY,
        home_score=None, away_score=None, tenant_id="t-cam",
    ))
    session.flush()


def _frame(session, minute: float, created_at: datetime) -> None:
    session.add(models.TrackingFrameRow(
        sport=football.SPORT_NAME, match_external_id=MATCH, timestamp=created_at,
        period=1, minute=minute, ball_x=50.0, ball_y=50.0,
        players_json=json.dumps([]), meta_json=None, created_at=created_at, tenant_id="t-cam",
    ))
    session.flush()


def _pass(session, minute: float) -> None:
    now = datetime.now(UTC)
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-cam", source="video",
        source_event_id=f"p{minute}", match_external_id=MATCH, team_external_id=HOME,
        player_external_id=1, event_type="pass", minute=minute, period=1,
        start_x=40.0, start_y=50.0, end_x=60.0, end_y=50.0, outcome="completed",
        body_part=None, pattern="regular", possession_id=1, is_goal=None, key_pass=False,
        raw_json=None, created_at=now,
    ))
    session.flush()


def test_clock_follows_latest_frame_and_measures_latency(session) -> None:
    _seed_match(session)
    feed = CameraLiveFeed(session, MATCH)
    assert feed.mode() == CAMERA_MODE
    assert feed.last_event_minute() == 0.0
    assert feed.clock().latency_seconds() is None and feed.clock().frames == 0

    now = datetime.now(UTC)
    _frame(session, 12.0, now - timedelta(seconds=200))
    _frame(session, 12.5, now - timedelta(seconds=90))
    clock = feed.clock()
    assert clock.latest_frame_minute == 12.5 and clock.frames == 2
    assert feed.last_event_minute() == 12.5
    lag = clock.latency_seconds(now=now)
    assert lag is not None and 89.0 <= lag <= 91.0


def test_refresh_picks_up_new_video_passes(session) -> None:
    _seed_match(session)
    feed = CameraLiveFeed(session, MATCH)
    assert feed.window(20.0).passes == []
    _pass(session, 10.0)
    _pass(session, 15.0)
    assert feed.window(20.0).passes == []          # yenilenmeden eski görünüm
    feed.refresh()
    assert [p.minute for p in feed.window(12.0).passes] == [10.0]
    assert len(feed.window(20.0).passes) == 2
    assert feed.running_score(20.0) == (0, 0)       # videodan gol okunmaz


def test_factory_builds_camera_feed_on_request(session) -> None:
    _seed_match(session)
    assert build_live_feed(session, MATCH, mode="camera").mode() == CAMERA_MODE
    # bilinmeyen mod → replay'e düşer (mevcut davranış korunur)
    assert build_live_feed(session, MATCH, mode="yok_boyle").mode() != CAMERA_MODE
