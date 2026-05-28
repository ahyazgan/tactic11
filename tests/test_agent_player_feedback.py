"""PlayerFeedbackAgent + TrainingPlanAgent tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents import PlayerFeedbackAgent, TrainingPlanAgent
from app.ai import AnthropicClient, ClaudeCommentator
from app.db import models
from app.sports import football


@pytest.fixture()
def feedback_agent():
    return PlayerFeedbackAgent(
        commentator=ClaudeCommentator(AnthropicClient(api_key=None)),
    )


@pytest.fixture()
def training_agent():
    return TrainingPlanAgent(
        commentator=ClaudeCommentator(AnthropicClient(api_key=None)),
    )


def _seed_match(session, match_id: int = 9001):
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
    session.commit()


def _add_event(session, *, match_id: int, ev_type: str, team: int,
               player: int = 100, sb_id: str = "e", minute: float = 10.0,
               outcome: str = "completed", is_goal: bool = False):
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id=sb_id,
        match_external_id=match_id, team_external_id=team,
        player_external_id=player, event_type=ev_type,
        minute=minute, period=1,
        start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
        outcome=outcome if ev_type != "shot" else ("goal" if is_goal else None),
        body_part="right_foot" if ev_type == "shot" else None,
        pattern="regular", possession_id=1,
        is_goal=is_goal if ev_type == "shot" else None,
        key_pass=False, raw_json=None,
        created_at=datetime.now(UTC),
    ))


def _add_appearance(session, *, match_id: int, player: int = 100, minutes: int = 90):
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME, tenant_id="t-default",
        match_external_id=match_id, team_external_id=11,
        player_external_id=player, minutes=minutes,
        kickoff=datetime.now(UTC) - timedelta(days=1),
    ))


# --------------------------------------------------------------------------- #
# PlayerFeedbackAgent
# --------------------------------------------------------------------------- #


def test_feedback_no_events_stub(session, feedback_agent):
    _seed_match(session)
    r = feedback_agent.run(session, context={
        "match_external_id": 9001, "player_external_id": 100,
    })
    assert r.output_json["events_loaded"] == 0
    assert "stub:player_feedback" in r.output_json["ai_brief"]


def test_feedback_full_report(session, feedback_agent):
    _seed_match(session)
    _add_appearance(session, match_id=9001, player=100, minutes=90)
    # 20 pas + 5 carry + 3 şut, oyuncu 100
    for i in range(20):
        _add_event(session, match_id=9001, ev_type="pass", team=11,
                   player=100, sb_id=f"p{i}", minute=float(5 + i * 2))
    for i in range(5):
        _add_event(session, match_id=9001, ev_type="carry", team=11,
                   player=100, sb_id=f"c{i}", minute=float(15 + i * 5))
    for i in range(3):
        _add_event(session, match_id=9001, ev_type="shot", team=11,
                   player=100, sb_id=f"s{i}", minute=float(30 + i * 5),
                   is_goal=(i == 0))
    session.commit()

    r = feedback_agent.run(session, context={
        "match_external_id": 9001, "player_external_id": 100,
    })
    out = r.output_json
    assert out["player_external_id"] == 100
    assert out["minutes_played"] == 90.0
    assert "metrics" in out
    assert "pass_alternatives_summary" in out
    assert out["pass_alternatives_summary"]["passes_analyzed"] == 20


def test_feedback_missing_context_raises(session, feedback_agent):
    _seed_match(session)
    with pytest.raises(ValueError, match="zorunlu"):
        feedback_agent.run(session, context={"match_external_id": 9001})


def test_feedback_missing_match_raises(session, feedback_agent):
    _seed_match(session)
    with pytest.raises(ValueError, match="yok"):
        feedback_agent.run(session, context={
            "match_external_id": 99999, "player_external_id": 100,
        })


# --------------------------------------------------------------------------- #
# TrainingPlanAgent
# --------------------------------------------------------------------------- #


def test_training_plan_no_events_stub(session, training_agent):
    _seed_match(session)
    r = training_agent.run(session, context={
        "my_team_external_id": 11, "opponent_external_id": 22,
    })
    assert r.output_json["events_loaded"] == 0


def test_training_plan_full_report(session, training_agent):
    """Rakip için event seed → drill önerileri gelir."""
    _seed_match(session, match_id=9101)
    # Rakip takım için event seed
    for i in range(50):
        _add_event(session, match_id=9101, ev_type="pass", team=22,
                   player=200, sb_id=f"opp_p{i}", minute=float(i),
                   outcome="completed")
    for i in range(20):
        _add_event(session, match_id=9101, ev_type="defensive_action",
                   team=22, player=200, sb_id=f"opp_d{i}",
                   minute=float(i * 3))
    session.commit()

    r = training_agent.run(session, context={
        "my_team_external_id": 11, "opponent_external_id": 22,
    })
    out = r.output_json
    assert "drills" in out
    assert "opponent_profile" in out
    assert len(out["drills"]) >= 1


def test_training_plan_missing_context_raises(session, training_agent):
    with pytest.raises(ValueError, match="zorunlu"):
        training_agent.run(session, context={"my_team_external_id": 11})
