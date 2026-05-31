"""Faz 5 chat tools — 13 yeni Sprint 1 tool wrapper testleri."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.assistant.tools import execute_tool, get_tool_schemas
from app.assistant.tools_v2 import (
    V2_TOOL_HANDLERS,
    V2_TOOL_SCHEMAS,
)
from app.db import models
from app.sports import football


def _seed_tenant_match(session, match_id: int = 9100):
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
    session.flush()


# --------------------------------------------------------------------------- #
# Registry doğrulama
# --------------------------------------------------------------------------- #


def test_v2_handlers_and_schemas_match():
    """13 schema = 13 handler; isim eşleşmesi."""
    schema_names = {s["name"] for s in V2_TOOL_SCHEMAS}
    handler_names = set(V2_TOOL_HANDLERS.keys())
    assert schema_names == handler_names
    assert len(schema_names) == 13


def test_get_tool_schemas_merges_v1_and_v2():
    """tools.get_tool_schemas v1 + v2 birlikte döner."""
    schemas = get_tool_schemas()
    names = {s["name"] for s in schemas}
    # v1 tool sample
    assert "get_team_form" in names
    # v2 tool sample
    assert "get_player_feedback" in names
    assert "get_set_piece_routine" in names
    assert "compare_players" in names


def test_execute_tool_routes_v2(session):
    """execute_tool v2 handler'a düşer."""
    _seed_tenant_match(session)
    out = execute_tool(
        session, "get_set_piece_routine",
        {"my_team_external_id": 11, "opponent_external_id": 22},
    )
    assert "info" in out or "top_recommendations" in out


def test_score_prediction_tool_registered_and_routes(session):
    """Yeni v1 tool get_score_prediction schema'da var ve execute_tool yönlendirir."""
    import json

    names = {s["name"] for s in get_tool_schemas()}
    assert "get_score_prediction" in names

    _seed_tenant_match(session, match_id=9200)
    out = json.loads(execute_tool(
        session, "get_score_prediction", {"match_external_id": 9200, "top_n": 3},
    ))
    assert out.get("match_id") == 9200
    assert "prob_btts" in out
    assert "top_scores" in out
    assert len(out["top_scores"]) <= 3


def test_season_projection_tool_registered_and_routes(session):
    """get_season_projection schema'da var ve execute_tool yönlendirir."""
    import json

    names = {s["name"] for s in get_tool_schemas()}
    assert "get_season_projection" in names

    _seed_tenant_match(session, match_id=9300)  # team 11 ev sahibi, FT 1-0 → 3 puan
    out = json.loads(execute_tool(
        session, "get_season_projection", {"team_external_id": 11, "target_points": 5},
    ))
    assert out.get("team_id") == 11
    assert out["current_points"] == 3
    assert "expected_final_points" in out
    assert out["points_target"]["target_points"] == 5


# --------------------------------------------------------------------------- #
# Tool davranışları (events yok / stub paths)
# --------------------------------------------------------------------------- #


def test_lineup_recommendation_invalid_team_returns_error(session):
    out = V2_TOOL_HANDLERS["get_lineup_recommendation"](
        session, team_external_id=99999,
    )
    assert "error" in out


def test_opponent_scout_no_upcoming(session):
    _seed_tenant_match(session)  # FT match only, no upcoming
    out = V2_TOOL_HANDLERS["get_opponent_scout"](
        session, team_external_id=11,
    )
    # Ya error ya info
    assert "info" in out or "error" in out


def test_training_plan_no_events(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["get_training_plan"](
        session, my_team_external_id=11, opponent_external_id=22,
    )
    # Agent stub mode → output döner
    assert "output" in out or "error" in out


def test_set_piece_routine_no_events(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["get_set_piece_routine"](
        session, my_team_external_id=11, opponent_external_id=22,
    )
    assert "info" in out


def test_player_feedback_no_events(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["get_player_feedback"](
        session, match_external_id=9100, player_external_id=5503,
    )
    assert "output" in out
    assert out["output"].get("events_loaded") == 0


def test_team_tactical_no_events(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["get_team_tactical"](
        session, team_external_id=11,
    )
    assert "info" in out


def test_team_tactical_with_events(session):
    """Event seed → PPDA + tempo + xT döner."""
    _seed_tenant_match(session)
    for i in range(20):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=9100, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(5 + i), period=1,
            start_x=50.0, start_y=50.0, end_x=60.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=1, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"d{i}",
            match_external_id=9100, team_external_id=11,
            player_external_id=1, event_type="defensive_action",
            minute=float(10 + i), period=1,
            start_x=40.0, start_y=50.0, end_x=None, end_y=None,
            outcome="successful", body_part=None, pattern="tackle",
            possession_id=None, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    session.commit()
    out = V2_TOOL_HANDLERS["get_team_tactical"](
        session, team_external_id=11, opponent_id=22,
    )
    assert "ppda" in out
    assert "tempo_label" in out
    assert "team_xt_total" in out


def test_compare_players_missing_target(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["compare_players"](
        session,
        target_player_external_id=99999,
        candidate_player_external_ids=[1, 2],
    )
    assert "error" in out


def test_compare_players_with_data(session):
    """Target ve aday için appearance seed → similarity döner."""
    _seed_tenant_match(session)
    now = datetime.now(UTC)
    for pid in (100, 200, 300):
        for i in range(3):
            session.add(models.PlayerAppearance(
                sport=football.SPORT_NAME, tenant_id="t-default",
                match_external_id=9100 + i, team_external_id=11,
                player_external_id=pid, minutes=90,
                kickoff=now - timedelta(days=i + 1),
            ))
    session.commit()
    out = V2_TOOL_HANDLERS["compare_players"](
        session,
        target_player_external_id=100,
        candidate_player_external_ids=[200, 300],
        min_minutes=60,
    )
    assert "matches" in out or "info" in out


def test_weekly_digest_with_league_id(session):
    _seed_tenant_match(session)
    out = V2_TOOL_HANDLERS["get_weekly_digest"](
        session, league_external_id=203,
    )
    # League yoksa hata, ama tool çağrısı başarısız değil (hata input olarak döner)
    assert "output" in out or "error" in out


def test_injury_load_no_team(session):
    out = V2_TOOL_HANDLERS["get_injury_load"](
        session, team_external_id=99999,
    )
    # Boş takım → output döner (boş liste) veya error
    assert "output" in out or "error" in out
