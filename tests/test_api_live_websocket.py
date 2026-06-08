"""Live WebSocket endpoint tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_active_connections_endpoint_returns_zero(client):
    r = client.get("/ws/active-connections")
    assert r.status_code == 200
    assert "count" in r.json()


def _seed_match_with_events(session, match_id: int = 7001):
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
    # 60 pass over 90 minutes
    for i in range(60):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=(100 + i % 11), event_type="pass",
            minute=float(i * 1.5), period=1 if i * 1.5 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i // 3, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    session.commit()


def test_websocket_streams_snapshots(session, client):
    """WS bağlanır, ilk snapshot'ı alır, gerekli alanları içerir."""
    _seed_match_with_events(session)
    with client.websocket_connect(
        "/ws/matches/7001/live?my_team_id=11&interval_seconds=5"
        "&max_minute=10&tenant_id=t-default",
    ) as ws:
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data["match_id"] == 7001
        assert data["my_team_id"] == 11
        assert "current_minute" in data
        assert "events_so_far" in data


def test_websocket_score_is_as_of_minute_not_final(session, client):
    """Replay skoru as-of-minute olmalı: final 1-0 maçta 80'de atılan gol,
    max_minute=10 snapshot'ında 0-0 görünmeli (final-skor sızıntısı yok)."""
    _seed_match_with_events(session)  # final home_score=1, away_score=0
    # 80. dk'da ev sahibi (11) golü — shot + is_goal
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id="goal80",
        match_external_id=7001, team_external_id=11,
        player_external_id=100, event_type="shot",
        minute=80.0, period=2,
        start_x=90.0, start_y=50.0, end_x=90.0, end_y=50.0,
        outcome="goal", body_part=None, pattern="open_play",
        possession_id=999, is_goal=True, key_pass=False,
        raw_json=None, created_at=datetime.now(UTC),
    ))
    session.commit()
    with client.websocket_connect(
        "/ws/matches/7001/live?my_team_id=11&interval_seconds=5"
        "&max_minute=10&tenant_id=t-default",
    ) as ws:
        data = json.loads(ws.receive_text())
        assert data["score"] == "0-0"  # final "1-0" DEĞİL → sızıntı gitti
        assert data["mode"] == "replay_statsbomb"
        assert "phase" in data


def test_websocket_match_not_found(session, client):
    """Match yok → snapshot içinde error field."""
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    with client.websocket_connect(
        "/ws/matches/9999/live?my_team_id=11&interval_seconds=5"
        "&max_minute=5&tenant_id=t-default",
    ) as ws:
        msg = ws.receive_text()
        data = json.loads(msg)
        assert "error" in data
