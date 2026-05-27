"""/players/{id}/load endpoint testleri."""

from __future__ import annotations

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


def _seed_apps(session, player_id: int, *, n: int = 3, minutes_each: int = 90, days_ago: int = 7):
    now = datetime.now(UTC)
    for i in range(n):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME,
            player_external_id=player_id,
            match_external_id=1000 + i,
            minutes=minutes_each,
            kickoff=now - timedelta(days=days_ago - i),
        ))
    session.flush()


def test_player_load_404_when_no_appearances(client):
    r = client.get("/players/777/load")
    assert r.status_code == 404


def test_player_load_returns_engine_value(session, client):
    _seed_apps(session, player_id=7, n=3, minutes_each=90, days_ago=7)
    r = client.get("/players/7/load?window_days=14")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.load"
    assert body["audit"]["subject_id"] == 7
    v = body["value"]
    assert v["matches_in_window"] == 3
    assert v["minutes_in_window"] == 270
    assert v["minutes_per_match"] == 90.0


def test_player_load_high_load_flag(session, client):
    """6 maç × 90 dk / 14 gün * 7 = 270 → eşikte True."""
    _seed_apps(session, player_id=8, n=6, minutes_each=90, days_ago=10)
    r = client.get("/players/8/load?window_days=14")
    body = r.json()
    assert body["value"]["high_load"] is True


def test_player_load_window_filter(session, client):
    """window_days=7 → 10 gün önceki maç dışarıda."""
    now = datetime.now(UTC)
    session.add_all([
        models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=9,
            match_external_id=1, minutes=90, kickoff=now - timedelta(days=2),
        ),
        models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=9,
            match_external_id=2, minutes=90, kickoff=now - timedelta(days=10),
        ),
    ])
    session.flush()
    r = client.get("/players/9/load?window_days=7")
    body = r.json()
    # Sadece son 2 günlük maç pencere içinde
    assert body["value"]["matches_in_window"] == 1
