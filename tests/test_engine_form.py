from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
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


# ---- v2 alanları -----------------------------------------------------------


def test_form_counts_clean_sheets_and_per_match():
    matches = [
        _match(1, home=611, away=607, home_score=2, away_score=0, days_ago=10),  # CS (home)
        _match(2, home=614, away=611, home_score=1, away_score=3, days_ago=7),   # CS yok
        _match(3, home=611, away=998, home_score=4, away_score=0, days_ago=3),   # CS (home)
    ]
    f = compute_form(611, matches, last_n=5).value
    assert f.clean_sheets == 2
    assert f.goals_for_per_match == 3.0  # round((2+3+4)/3, 3)
    assert f.goals_against_per_match == 0.333  # round((0+1+0)/3, 3)


def test_form_momentum_positive_when_recent_better():
    # 5 maç: ilk 2 mağlubiyet, son 3 galibiyet → recent>older, momentum > 0
    matches = [
        _match(1, home=611, away=607, home_score=3, away_score=0, days_ago=1),
        _match(2, home=611, away=614, home_score=2, away_score=0, days_ago=3),
        _match(3, home=611, away=998, home_score=4, away_score=1, days_ago=5),
        _match(4, home=998, away=611, home_score=3, away_score=0, days_ago=10),
        _match(5, home=607, away=611, home_score=2, away_score=0, days_ago=15),
    ]
    f = compute_form(611, matches, last_n=5).value
    assert f.recent_ppg == pytest.approx(3.0)  # son 3 maç hep W
    # older 2 maç hep L → older_ppg=0
    assert f.momentum == pytest.approx(3.0)


def test_form_streak_positive_for_consecutive_wins():
    matches = [
        _match(1, home=611, away=607, home_score=2, away_score=0, days_ago=1),  # W
        _match(2, home=611, away=614, home_score=3, away_score=1, days_ago=3),  # W
        _match(3, home=998, away=611, home_score=0, away_score=2, days_ago=5),  # W
        _match(4, home=998, away=611, home_score=2, away_score=1, days_ago=10), # L
    ]
    f = compute_form(611, matches, last_n=5).value
    assert f.last_results == ["W", "W", "W", "L"]
    assert f.current_streak == 3
    assert f.current_unbeaten == 3


def test_form_streak_negative_for_consecutive_losses():
    matches = [
        _match(1, home=998, away=611, home_score=2, away_score=0, days_ago=1),   # L
        _match(2, home=611, away=607, home_score=0, away_score=3, days_ago=3),   # L
        _match(3, home=611, away=614, home_score=2, away_score=0, days_ago=10),  # W
    ]
    f = compute_form(611, matches, last_n=5).value
    assert f.current_streak == -2
    assert f.current_unbeaten == 0  # son maç L


def test_form_streak_zero_when_last_match_draw():
    matches = [
        _match(1, home=611, away=607, home_score=1, away_score=1, days_ago=1),   # D
        _match(2, home=611, away=614, home_score=2, away_score=0, days_ago=3),   # W
    ]
    f = compute_form(611, matches, last_n=5).value
    assert f.current_streak == 0
    assert f.current_unbeaten == 2  # D + W
