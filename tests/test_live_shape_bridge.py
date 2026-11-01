"""Takip kareleri (DB) → şekil bekçisi bloğu ve uyarıları; kamera WS'i bunu taşır."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.api.live_shape_bridge import shape_watch_for
from app.api.tracking import frames_in_window
from app.db import models
from app.sports import football
from tests.test_api_live_websocket import client  # noqa: F401
from tests.test_shape_watch import _home_defending

MATCH, HOME, AWAY = 9, 11, 22


def _seed(session, source: str = "video_tracking", recent_back: float = 28.0) -> None:
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X", settings_json="{}",
                              active=True, created_at=now))
    session.add(models.Match(sport=football.SPORT_NAME, external_id=MATCH, league_external_id=1, season=2026,
                             kickoff=now, status="LIVE", home_team_external_id=HOME, away_team_external_id=AWAY,
                             home_score=None, away_score=None, tenant_id="t-default"))
    t = 0.0
    while t <= 30.0:
        f = _home_defending(t, back=recent_back if t >= 25 else 36.0, gap=10.0, width=40)
        session.add(models.TrackingFrameRow(
            sport=football.SPORT_NAME, match_external_id=MATCH, timestamp=now + timedelta(seconds=t * 60),
            period=1, minute=round(t, 2), ball_x=None, ball_y=None,
            players_json=json.dumps([p.model_dump() for p in f.players]),
            meta_json=json.dumps({"source": source, "possession_team_external_id": AWAY}),
            created_at=now, tenant_id="t-default"))
        t += 0.1
    session.commit()


def test_spread_reads_the_whole_window(session) -> None:
    _seed(session)
    tail = frames_in_window(session, MATCH, 0, 30, limit=50)
    spread = frames_in_window(session, MATCH, 0, 30, limit=50, spread=True)
    assert min(f.minute for f in tail) >= 25
    assert min(f.minute for f in spread) < 2 and len(spread) <= 50


def test_shape_watch_block_and_alert_from_db(session) -> None:
    _seed(session)
    block, alerts = shape_watch_for(session, MATCH, home_team_id=HOME, away_team_id=AWAY, my_team_id=HOME,
                                    minute=30.0)
    assert block is not None
    assert block["teams"][0]["metrics"]["block_depth"]["delta"] == -8.0
    assert [a["type"] for a in alerts] == ["shape_block_depth"]


def test_event_anchored_frames_are_skipped(session) -> None:
    _seed(session, source="statsbomb_360")
    assert shape_watch_for(session, MATCH, home_team_id=HOME, away_team_id=AWAY, my_team_id=HOME,
                           minute=30.0) == (None, [])


def test_camera_websocket_carries_shape_watch(session, client) -> None:  # noqa: F811
    _seed(session)
    with client.websocket_connect(
        f"/ws/matches/{MATCH}/live?my_team_id={HOME}&interval_seconds=5&tenant_id=t-default&feed=camera",
    ) as ws:
        data = json.loads(ws.receive_text())
    assert data["source"]["kind"] == "camera"
    assert "shape_watch" in data
    assert any(a["type"] == "shape_block_depth" for a in data["live_alerts"]["alerts"])
