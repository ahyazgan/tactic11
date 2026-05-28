"""Tactical profile batch endpoints (Wave 3 deliverable)."""

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


def _seed_basic(session):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=1001,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=2, away_score=1, tenant_id="t-default",
    ))
    session.flush()


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               player: int = 10, sb_id: str = "e1", pattern: str = "regular",
               outcome: str = "completed", is_goal: bool = False,
               poss: int | None = None, minute: float = 10.0):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=minute, period=1,
        start_x=50.0, start_y=50.0, end_x=60.0, end_y=50.0,
        outcome=outcome, body_part="right_foot" if ev_type == "shot" else None,
        pattern=pattern, possession_id=poss,
        is_goal=is_goal if ev_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))


def test_team_tactical_profile_empty_returns_note(client):
    _seed_basic_session = None  # placeholder
    r = client.get("/admin/teams/11/tactical-profile?last_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["team_id"] == 11
    assert body["events_loaded"] == 0


def test_team_tactical_profile_returns_engines(session, client):
    _seed_basic(session)
    # 30 pas + 10 carry + 15 def + 5 shot
    for i in range(30):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"p{i}", outcome="completed", poss=i // 3,
                   minute=float(i % 90))
    for i in range(10):
        _add_event(session, match_id=1001, ev_type="carry", team=11,
                   sb_id=f"c{i}", poss=i)
    for i in range(15):
        _add_event(session, match_id=1001, ev_type="defensive_action",
                   team=11, sb_id=f"d{i}", pattern="tackle",
                   outcome="successful")
    for i in range(5):
        _add_event(session, match_id=1001, ev_type="shot", team=11,
                   sb_id=f"s{i}", pattern="open_play", is_goal=(i == 0))
    session.commit()

    r = client.get("/admin/teams/11/tactical-profile?last_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["events_loaded"] == 60
    prof = body["tactical_profile"]
    # 19 takım engine
    expected = {
        "ppda", "pressing_trigger", "defensive_line", "compactness",
        "transition", "recovery_zone_heat", "counter_press_triggers",
        "direct_play", "tempo", "possession_quality", "channel_preference",
        "final_third_entries", "cross_effectiveness", "cutback_frequency",
        "defensive_duels", "press_resistance", "set_piece_zones",
        "build_up_pattern", "team_xt",
    }
    assert expected.issubset(set(prof.keys()))


def test_team_tactical_profile_with_opponent_adds_field_tilt(session, client):
    _seed_basic(session)
    _add_event(session, match_id=1001, ev_type="pass", team=11, sb_id="p1")
    _add_event(session, match_id=1001, ev_type="pass", team=22, sb_id="p2")
    session.commit()

    r = client.get("/admin/teams/11/tactical-profile?opponent_id=22")
    body = r.json()
    assert "field_tilt" in body["tactical_profile"]
    assert "coaching_identity" in body["tactical_profile"]


def test_player_tactical_profile_empty(client):
    r = client.get("/admin/players/100/tactical-profile")
    assert r.status_code == 200
    assert r.json()["events_loaded"] == 0


def test_player_tactical_profile_with_appearance(session, client):
    _seed_basic(session)
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=1001, team_external_id=11,
        player_external_id=100, minutes=90,
        kickoff=datetime.now(UTC) - timedelta(days=1),
    ))
    for i in range(20):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   player=100, sb_id=f"p{i}",
                   outcome="completed", poss=i // 2)
    session.commit()

    r = client.get("/admin/players/100/tactical-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["events_loaded"] >= 20
    assert body["meta"]["team_external_id"] == 11
    prof = body["tactical_profile"]
    for key in ("player_xt", "player_xa", "press_resistance",
                "overperformance", "progressive_passes",
                "carries_into_final_third", "off_ball_runs"):
        assert key in prof


def test_match_dominance_endpoint_404(client):
    r = client.get("/admin/matches/9999/dominance")
    assert r.status_code == 404


def test_match_dominance_endpoint(session, client):
    _seed_basic(session)
    for i in range(10):
        _add_event(session, match_id=1001, ev_type="pass", team=11,
                   sb_id=f"hp{i}", outcome="completed")
        _add_event(session, match_id=1001, ev_type="pass", team=22,
                   sb_id=f"ap{i}", outcome="completed")
    for i in range(3):
        _add_event(session, match_id=1001, ev_type="shot", team=11,
                   sb_id=f"hs{i}", pattern="open_play", is_goal=(i == 0))
    session.commit()

    r = client.get("/admin/matches/1001/dominance")
    assert r.status_code == 200
    body = r.json()
    assert body["match_id"] == 1001
    assert body["home_team_id"] == 11
    assert body["away_team_id"] == 22
    assert "match_dominance" in body
    assert "match_phases" in body
