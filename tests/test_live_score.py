"""running_score_as_of — as-of-minute koşan skor (saf helper).

Replay'de final skoru göstermek yerine, o dakikaya kadarki gollerden gerçek
oyun durumunu türetir. Bu testler sızıntının (final skor) gittiğini doğrular.
"""
from __future__ import annotations

from app.domain import Shot
from app.engine.live_score import running_score_as_of

HOME = 10
AWAY = 20


def _goal(minute: float, team_id: int | None) -> Shot:
    return Shot(
        sport="football", match_external_id=1, player_external_id=1,
        minute=minute, x=90.0, y=50.0, is_goal=True, team_external_id=team_id,
    )


def _miss(minute: float, team_id: int | None) -> Shot:
    return Shot(
        sport="football", match_external_id=1, player_external_id=1,
        minute=minute, x=90.0, y=50.0, is_goal=False, team_external_id=team_id,
    )


def test_no_goals_returns_zero_zero() -> None:
    shots = [_miss(10, HOME), _miss(30, AWAY)]
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=90.0,
    ) == (0, 0)


def test_goal_after_current_minute_not_counted() -> None:
    # Gol 80'de; 10. dk snapshot'ı hâlâ 0-0 olmalı (sızıntı yok).
    shots = [_goal(80, HOME)]
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=10.0,
    ) == (0, 0)
    # 85. dk'da artık sayılır.
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=85.0,
    ) == (1, 0)


def test_goals_attributed_to_correct_team() -> None:
    shots = [_goal(20, HOME), _goal(35, AWAY), _goal(70, HOME)]
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=90.0,
    ) == (2, 1)


def test_boundary_minute_inclusive() -> None:
    shots = [_goal(45, AWAY)]
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=45.0,
    ) == (0, 1)


def test_none_team_goal_skipped() -> None:
    # team_external_id=None → takıma atfedilemez, skora katılmaz.
    shots = [_goal(20, None), _goal(30, HOME)]
    assert running_score_as_of(
        shots, home_team_id=HOME, away_team_id=AWAY, current_minute=90.0,
    ) == (1, 0)
