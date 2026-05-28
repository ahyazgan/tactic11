"""GamePlanAgent + Sprint 2 endpoint tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents import GamePlanAgent
from app.ai import AnthropicClient, ClaudeCommentator
from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def agent():
    return GamePlanAgent(
        commentator=ClaudeCommentator(AnthropicClient(api_key=None)),
    )


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
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.flush()


def _seed_match_events(session, *, match_id: int, team: int, opp: int):
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=match_id % 10 + 1), status="FT",
        home_team_external_id=team, away_team_external_id=opp,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    for i in range(15):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"m{match_id}_p{i}",
            match_external_id=match_id, team_external_id=team,
            player_external_id=1, event_type="pass",
            minute=float(5 + i), period=1,
            start_x=50.0, start_y=50.0, end_x=80.0, end_y=15.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=1, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    for i in range(8):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"m{match_id}_d{i}",
            match_external_id=match_id, team_external_id=opp,
            player_external_id=2, event_type="defensive_action",
            minute=float(10 + i), period=1,
            start_x=30.0, start_y=85.0, end_x=None, end_y=None,
            outcome="successful", body_part=None, pattern="tackle",
            possession_id=None, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))


# --------------------------------------------------------------------------- #
# GamePlanAgent
# --------------------------------------------------------------------------- #


def test_game_plan_missing_context_raises(session, agent):
    _seed(session)
    with pytest.raises(ValueError, match="zorunlu"):
        agent.run(session, context={"my_team_external_id": 11})


def test_game_plan_no_events_scenario_only(session, agent):
    """Event yok → matchup/set_piece None, ama senaryo planı her zaman var."""
    _seed(session)
    session.commit()
    r = agent.run(session, context={
        "my_team_external_id": 11, "opponent_external_id": 22,
    })
    out = r.output_json
    assert out["scenario_plan"] is not None
    assert "leading" in out["scenario_plan"]
    assert "trailing" in out["scenario_plan"]
    assert "stub:game_plan" in out["ai_brief"]


def test_game_plan_with_events(session, agent):
    """Event seed → matchup grid + set-piece dolu."""
    _seed(session)
    # Hem bizim hem rakip için event (matchup grid 2 takım ister)
    _seed_match_events(session, match_id=5001, team=11, opp=22)
    _seed_match_events(session, match_id=5002, team=22, opp=11)
    session.commit()
    r = agent.run(session, context={
        "my_team_external_id": 11, "opponent_external_id": 22,
    })
    out = r.output_json
    assert out["matchup_grid"] is not None
    assert "best_channel" in out["matchup_grid"]


def test_game_plan_with_squad(session, agent):
    _seed(session)
    session.commit()
    r = agent.run(session, context={
        "my_team_external_id": 11, "opponent_external_id": 22,
        "squad": [
            {"player_id": 1, "injured": True},
            {"player_id": 2, "risk_level": "low"},
        ],
    })
    out = r.output_json
    assert out["available_squad"] is not None
    assert out["available_squad"]["unavailable_count"] == 1


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


def test_matchup_grid_endpoint_no_events(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/teams/11/matchup-grid?opponent_id=22")
    assert r.status_code == 200
    assert "note" in r.json()


def test_game_plan_endpoint_validates(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/game-plan", json={})
    assert r.status_code == 400


def test_game_plan_endpoint_works(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/game-plan", json={
        "opponent_external_id": 22,
        "squad": [{"player_id": 1, "risk_level": "low"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["scenario_plan"] is not None
    assert body["available_squad"]["available_count"] == 1


def test_available_squad_endpoint(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/available-squad", json={
        "squad": [
            {"player_id": 1, "injured": True},
            {"player_id": 2, "risk_level": "extreme"},
            {"player_id": 3, "risk_level": "low"},
        ],
    })
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["available_count"] == 1
    assert v["doubtful_count"] == 1
    assert v["unavailable_count"] == 1


def test_available_squad_empty_rejects(session, client):
    _seed(session)
    session.commit()
    r = client.post("/admin/teams/11/available-squad", json={"squad": []})
    assert r.status_code == 400


def test_proactive_alerts_endpoint(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/teams/11/proactive-alerts")
    assert r.status_code == 200
    assert "value" in r.json()


def test_daily_briefing_coach(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/daily-briefing?team_id=11&role=coach")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "coach"
    assert "todo" in body
    assert len(body["todo"]) > 0


def test_daily_briefing_admin(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/daily-briefing?team_id=11&role=admin")
    body = r.json()
    assert "ops" in body


def test_daily_briefing_analyst(session, client):
    _seed(session)
    session.commit()
    r = client.get("/admin/daily-briefing?team_id=11&role=analyst")
    body = r.json()
    assert "data" in body
