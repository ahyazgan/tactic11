"""engine.cross_effectiveness tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.cross_effectiveness import compute_cross_effectiveness


def _cross(team: int, end_y: float, minute: float = 10.0, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=85, start_y=15, end_x=95, end_y=end_y,
        pass_type="cross", completed=completed,
    )


def _shot(minute: float, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=95, y=50, is_goal=is_goal,
    )


def test_cross_near_post_paired_with_shot():
    crosses = [_cross(11, 20)]   # near post
    shots = [_shot(10.05, is_goal=True)]
    r = compute_cross_effectiveness(11, crosses, shots).value
    assert r.total_crosses == 1
    assert r.shots_from_crosses == 1
    assert r.goals_from_crosses == 1


def test_cross_outside_window_not_paired():
    crosses = [_cross(11, 50)]
    shots = [_shot(15.0)]  # 5 dakika sonra
    r = compute_cross_effectiveness(11, crosses, shots).value
    assert r.shots_from_crosses == 0


def test_zone_classification():
    crosses = [_cross(11, 20), _cross(11, 50), _cross(11, 80)]
    r = compute_cross_effectiveness(11, crosses, []).value
    zones = {z.zone: z.crosses for z in r.by_zone}
    assert zones["near_post"] == 1
    assert zones["central"] == 1
    assert zones["far_post"] == 1


def test_opponent_excluded():
    crosses = [_cross(22, 50)]
    r = compute_cross_effectiveness(11, crosses, []).value
    assert r.total_crosses == 0


def test_most_effective_zone_picks_highest_goal_conv():
    crosses = [_cross(11, 50, minute=10.0), _cross(11, 20, minute=20.0)]
    shots = [_shot(10.05, is_goal=False), _shot(20.05, is_goal=True)]
    r = compute_cross_effectiveness(11, crosses, shots).value
    assert r.most_effective_zone == "near_post"
