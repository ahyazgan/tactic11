"""/admin/players/{id}/tactical-trend endpoint tests."""

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


def _seed(session):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))


def _add_appearance(session, *, player: int, match_id: int, days_ago: int):
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=match_id, team_external_id=11,
        player_external_id=player, minutes=90,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
    ))


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               player: int, sb_id: str, outcome: str = "completed",
               pattern: str = "regular", start_x: float = 50,
               end_x: float = 80, end_y: float = 50, poss: int = 1):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=10.0, period=1,
        start_x=start_x, start_y=50.0, end_x=end_x, end_y=end_y,
        outcome=outcome, body_part=None, pattern=pattern,
        possession_id=poss, is_goal=None, key_pass=False,
        raw_json=None, created_at=datetime.now(UTC),
    ))


def test_player_trend_no_appearances(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/players/100/tactical-trend")
    assert r.status_code == 200
    assert r.json()["matches_analyzed"] == 0


def test_player_trend_with_3_matches(session, client):
    _seed(session)
    for mid, days in [(5001, 10), (5002, 5), (5003, 1)]:
        _add_appearance(session, player=100, match_id=mid, days_ago=days)
        for i in range(10):
            _add_event(session, match_id=mid, ev_type="pass", team=11,
                       player=100, sb_id=f"m{mid}_p{i}")
        for i in range(3):
            _add_event(session, match_id=mid, ev_type="carry", team=11,
                       player=100, sb_id=f"m{mid}_c{i}")
    session.commit()

    r = client.get("/admin/players/100/tactical-trend?last_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["matches_analyzed"] == 3
    assert "trends" in body
    expected = {"xt_added", "xa_total", "vaep_per_90",
                "progressive_per_90", "press_resistance"}
    assert set(body["trends"].keys()) == expected
    for _m, t in body["trends"].items():
        assert len(t["series"]) == 3
