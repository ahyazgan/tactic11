"""Faz 7 endpoint tests — live-decision (genişletilmiş) + set-piece/friction/referee."""
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


def _seed_match_events(session, match_id: int = 9400):
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
    for i in range(30):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 2), period=1 if i * 2 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=75.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()


def test_live_decision_includes_faz7(session, client):
    """live-decision artık spatial/matchup/score-time da döner."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9400/live-decision"
        "?my_team_id=11&current_minute=86&star_player_id=10"
    )
    assert r.status_code == 200
    body = r.json()
    assert "spatial_control" in body
    assert "live_matchup" in body
    assert "score_time_matrix" in body
    # 1-0 önde + 86. dk → see_out
    assert body["score_time_matrix"]["posture"] == "see_out"


def test_set_piece_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9400/set-piece?my_team_id=11&current_minute=70",
        json={
            "set_piece_won": "corner",
            "opponent_weak_zones": ["far_post"],
            "penalty_taker": {"player_id": 9, "fatigue": 0.9, "recent_accuracy": 0.5},
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opportunity"]["target_zone"] == "far_post"
    assert v["penalty_status"]["fit_to_take"] is False


def test_game_friction_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9400/game-friction?my_team_id=11&current_minute=70",
        json={"opponent_foul_zones": ["left_wing", "left_wing"]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["foul_hotspot"]["zone"] == "left_wing"


def test_referee_context_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9400/referee-context?my_team_id=11&current_minute=50",
        json={
            "cards_per_game": 5.0,
            "opponent_card_edge_players": [{"player_id": 4, "position_zone": "sağ bek"}],
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["strict_referee"] is True
    assert v["advantage_targets"][0]["player_external_id"] == 4


def test_set_piece_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/set-piece?my_team_id=11&current_minute=70",
        json={},
    )
    assert r.status_code == 404
