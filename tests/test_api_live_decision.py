"""Faz 6 live-decision endpoint tests."""
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
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_match_events(session, match_id: int = 9300):
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
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    for i in range(30):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 2), period=1 if i * 2 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()


def test_live_decision_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/matches/99999/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 404


def test_live_decision_no_events(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9300,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    session.commit()
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 200
    assert r.json()["events_loaded"] == 0


def test_live_decision_full_panel(session, client):
    _seed_match_events(session)
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=70")
    assert r.status_code == 200
    body = r.json()
    assert "momentum" in body
    assert "sub_timing" in body
    assert "tactical_triggers" in body
    assert "risk_monitor" in body


def test_opponent_reaction_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/opponent-reaction?my_team_id=11&current_minute=70&momentum_score=-0.5",
        json={"opponent_subs": [{"position_in": "F", "minute": 65}]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opp_subs_detected"] == 1
    assert v["momentum_break_advice"] is not None


def test_live_risk_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": [
            {"player_id": 100, "yellow_card": True, "duel_count": 5},
            {"player_id": 200, "fatigue": 0.85},
        ]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert len(v["card_flags"]) == 1
    assert len(v["injury_flags"]) == 1
    # Geride (1-2) + 80. dk → tempoyu artır
    assert "tempoyu artır" in v["time_management"]


def test_live_risk_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": []},
    )
    assert r.status_code == 404
