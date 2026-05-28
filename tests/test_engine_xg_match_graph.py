"""engine.xg_match_graph tests."""

from __future__ import annotations

from app.domain import Shot
from app.engine.xg_match_graph import (
    compute_match_xg_graph_split,
    compute_season_xg_difference,
)


def _shot(minute: float, x: float = 88.0, y: float = 50.0, is_goal: bool = False, mid: int = 1) -> Shot:
    return Shot(
        sport="football", match_external_id=mid, player_external_id=10,
        minute=minute, x=x, y=y, body_part="right_foot",
        pattern="open_play", is_goal=is_goal,
    )


def test_split_graph_merges_chronologically():
    """Home + away şutlar dakika sırasına göre merge edilmeli."""
    home = [_shot(20.0, x=85), _shot(60.0, x=85)]
    away = [_shot(35.0, x=85)]
    r = compute_match_xg_graph_split(
        match_external_id=1, home_team_id=10, away_team_id=20,
        home_shots=home, away_shots=away,
    )
    g = r.value
    assert len(g.timeline) == 3
    minutes = [p.minute for p in g.timeline]
    assert minutes == sorted(minutes)


def test_cumulative_xg_increases():
    """Her şut sonrası kümülatif xG artmalı."""
    home = [_shot(20.0), _shot(40.0), _shot(60.0)]
    r = compute_match_xg_graph_split(1, 10, 20, home, [])
    home_points = [p.cumulative_xg for p in r.value.timeline]
    assert home_points[0] < home_points[1] < home_points[2]


def test_goal_flag_propagated():
    home = [_shot(20.0, is_goal=True), _shot(40.0, is_goal=False)]
    r = compute_match_xg_graph_split(1, 10, 20, home, [])
    assert r.value.timeline[0].is_goal is True
    assert r.value.timeline[1].is_goal is False
    assert r.value.home_actual_goals == 1


def test_total_xg_matches_sum():
    home = [_shot(20.0, x=88), _shot(40.0, x=88)]
    r = compute_match_xg_graph_split(1, 10, 20, home, [])
    sum_xg = sum(p.cumulative_xg - (r.value.timeline[i-1].cumulative_xg if i > 0 else 0)
                 for i, p in enumerate(r.value.timeline))
    assert abs(r.value.home_total_xg - sum_xg) < 0.01


def test_team_attribution():
    """Home şutlar home team_id, away şutlar away team_id'ye."""
    home = [_shot(20.0)]
    away = [_shot(30.0)]
    r = compute_match_xg_graph_split(1, 10, 20, home, away)
    home_point = next(p for p in r.value.timeline if p.minute == 20.0)
    away_point = next(p for p in r.value.timeline if p.minute == 30.0)
    assert home_point.team_external_id == 10
    assert away_point.team_external_id == 20


def test_empty_shots_zero_graph():
    r = compute_match_xg_graph_split(1, 10, 20, [], [])
    assert r.value.timeline == []
    assert r.value.home_total_xg == 0
    assert r.value.away_total_xg == 0


# --------------------------------------------------------------------------- #
# Season xG difference
# --------------------------------------------------------------------------- #


def test_season_xgd_overperformance_positive():
    """xG 5 vs xG against 3 = xGD 2; actual 7-3 = 4 → overperf +2 (şanslı)."""
    for_shots = [_shot(20.0) for _ in range(10)]
    against_shots = [_shot(30.0) for _ in range(5)]
    r = compute_season_xg_difference(
        team_external_id=10,
        team_shots_for=for_shots,
        team_shots_against=against_shots,
        actual_goals_for=7, actual_goals_against=3,
        matches_analyzed=10,
    )
    assert r.value.xg_for > 0
    assert r.value.xg_against > 0
    assert r.value.xg_difference > 0  # for > against
    assert r.value.goals_for == 7
    assert r.value.matches_analyzed == 10


def test_season_xgd_audit():
    r = compute_season_xg_difference(
        team_external_id=10, team_shots_for=[], team_shots_against=[],
        actual_goals_for=0, actual_goals_against=0, matches_analyzed=10,
    )
    assert r.audit.engine == "engine.xg_match_graph"
    assert "xg_difference" in r.audit.value
