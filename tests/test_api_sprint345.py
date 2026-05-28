"""Sprint 3-5 endpoint tests (injury-risk, squad-depth, rotation, season, transfer, decision)."""
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


def _seed(session):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.flush()


def _seed_appearances(session, *, player: int = 100, team: int = 11, n: int = 6):
    now = datetime.now(UTC)
    for i in range(n):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, tenant_id="t-default",
            match_external_id=7000 + i, team_external_id=team,
            player_external_id=player, minutes=90,
            kickoff=now - timedelta(days=i),
        ))


def test_injury_risk_404_no_appearances(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/players/999/injury-risk")
    assert r.status_code == 404


def test_injury_risk_endpoint(session, client):
    _seed(session)
    _seed_appearances(session, player=100, n=6)
    session.commit()
    r = client.get("/admin/players/100/injury-risk?age=33")
    assert r.status_code == 200
    v = r.json()["value"]
    assert "risk_score" in v
    assert "risk_level" in v


def test_squad_depth_endpoint(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/squad-depth", json={
        "squad": [
            {"player_id": 1, "position": "G", "age": 28},
            {"player_id": 2, "position": "D", "age": 34},
            {"player_id": 3, "position": "D", "age": 33},
        ],
    })
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["total_players"] == 3


def test_squad_depth_empty_rejects(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/squad-depth", json={"squad": []})
    assert r.status_code == 400


def test_rotation_plan_endpoint(session, client):
    _seed(session)
    _seed_appearances(session, player=100, team=11, n=6)
    session.commit()
    r = client.get("/admin/teams/11/rotation-plan")
    assert r.status_code == 200
    assert "value" in r.json()


def test_season_calendar_no_matches(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/teams/11/season-calendar")
    assert r.status_code == 200
    assert "note" in r.json()


def test_season_calendar_with_matches(session, client):
    _seed(session)
    now = datetime.now(UTC)
    for i in range(3):
        session.add(models.Match(
            sport=football.SPORT_NAME, external_id=8000 + i,
            league_external_id=203, season=2024,
            kickoff=now + timedelta(days=i * 3 + 1), status="NS",
            home_team_external_id=11, away_team_external_id=22 + i,
            tenant_id="t-default",
        ))
    session.commit()
    r = client.get("/admin/teams/11/season-calendar")
    assert r.status_code == 200
    body = r.json()
    assert "schedule" in body
    assert "fixture_difficulty" in body


def test_transfer_targets_404(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/players/999/transfer-targets")
    assert r.status_code == 404


def test_transfer_targets_endpoint(session, client):
    _seed(session)
    now = datetime.now(UTC)
    for pid in (100, 200, 300):
        for i in range(3):
            session.add(models.PlayerAppearance(
                sport=football.SPORT_NAME, tenant_id="t-default",
                match_external_id=7000 + i, team_external_id=11,
                player_external_id=pid, minutes=90,
                kickoff=now - timedelta(days=i + 1),
            ))
    session.commit()
    r = client.get("/admin/players/100/transfer-targets?min_minutes=60")
    assert r.status_code == 200
    assert "targets" in r.json()


def test_decision_dashboard_no_matches(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/teams/11/decision-dashboard")
    assert r.status_code == 200
    assert "note" in r.json()


def test_decision_dashboard_with_decisions(session, client):
    _seed(session)
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=8500,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    session.add(models.Decision(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=8500, team_external_id=11,
        minute=65.0, period=2, decision_type="substitution",
        subject_player_external_id=100, related_player_external_id=200,
        notes="test", created_at=now,
    ))
    session.commit()
    r = client.get("/admin/teams/11/decision-dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["total_decisions"] == 1
    assert body["by_type"]["substitution"] == 1
