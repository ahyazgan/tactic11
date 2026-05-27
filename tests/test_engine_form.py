from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import Match
from app.engine.form import compute_form
from app.sports import football


def _match(
    ext_id: int,
    *,
    home: int,
    away: int,
    home_score: int | None,
    away_score: int | None,
    days_ago: int,
    status: str = "FT",
) -> Match:
    return Match(
        sport=football.SPORT_NAME,
        external_id=ext_id,
        league_external_id=203,
        season=2024,
        kickoff=datetime.now(timezone.utc) - timedelta(days=days_ago),
        status=status,
        home_team_external_id=home,
        away_team_external_id=away,
        home_score=home_score,
        away_score=away_score,
    )


def test_form_counts_wd_l_and_goal_diff():
    matches = [
        _match(1, home=611, away=607, home_score=2, away_score=1, days_ago=10),  # W (home)
        _match(2, home=614, away=611, home_score=1, away_score=3, days_ago=7),   # W (away)
        _match(3, home=611, away=998, home_score=0, away_score=0, days_ago=3),   # D (home)
        _match(4, home=998, away=611, home_score=2, away_score=0, days_ago=1),   # L (away)
    ]
    res = compute_form(611, matches, last_n=10)
    f = res.value
    assert f.matches_played == 4
    assert (f.wins, f.draws, f.losses) == (2, 1, 1)
    assert f.goals_for == 5
    assert f.goals_against == 4
    assert f.goal_diff == 1
    assert f.points == 7
    assert f.points_per_game == pytest.approx(1.75)
    assert f.last_results == ["L", "D", "W", "W"]  # newest first


def test_form_filters_unfinished_and_respects_last_n():
    matches = [
        _match(1, home=611, away=607, home_score=2, away_score=1, days_ago=20),
        _match(2, home=611, away=614, home_score=None, away_score=None, days_ago=5, status="NS"),
        _match(3, home=998, away=611, home_score=0, away_score=3, days_ago=10),
        _match(4, home=611, away=998, home_score=1, away_score=1, days_ago=2),
    ]
    res = compute_form(611, matches, last_n=2)
    assert res.value.matches_played == 2
    assert res.value.last_results == ["D", "W"]  # 2 newest finished


def test_audit_carries_inputs_and_formula():
    matches = [_match(1, home=611, away=607, home_score=2, away_score=1, days_ago=1)]
    res = compute_form(611, matches)
    a = res.audit
    assert a.engine == "engine.form"
    assert a.subject_id == 611
    assert a.metric == "form_report"
    assert a.inputs["considered_match_ids"] == [1]
    assert "ppg" in a.formula
