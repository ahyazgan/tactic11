"""engine.cutback_frequency tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.cutback_frequency import compute_cutback_frequency


def _p(team: int, sx: float, sy: float, ex: float, ey: float,
       minute: float = 10.0) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
    )


def _shot(minute: float, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=88, y=50, is_goal=is_goal,
    )


def test_classic_cutback_left_to_center():
    """Sol kanattan dirğri ceza sahası ortasına geri pas."""
    passes = [_p(11, 92, 15, 87, 50)]  # x: 92→87 (geri); y: 15→50 (orta)
    r = compute_cutback_frequency(11, passes, []).value
    assert r.cutbacks == 1


def test_forward_pass_not_cutback():
    """Geriye değil, ileriye pas → cutback değil."""
    passes = [_p(11, 88, 15, 93, 50)]  # x ileri
    r = compute_cutback_frequency(11, passes, []).value
    assert r.cutbacks == 0


def test_central_pass_not_cutback():
    """Yan çizgide değil orta sahadan başlıyor."""
    passes = [_p(11, 88, 50, 87, 50)]
    r = compute_cutback_frequency(11, passes, []).value
    assert r.cutbacks == 0


def test_cutback_with_shot():
    passes = [_p(11, 92, 15, 87, 50, minute=10.0)]
    shots = [_shot(10.05, is_goal=True)]
    r = compute_cutback_frequency(11, passes, shots).value
    assert r.cutbacks == 1
    assert r.shots_from_cutbacks == 1
    assert r.goals_from_cutbacks == 1


def test_opponent_excluded():
    passes = [_p(22, 92, 15, 87, 50)]
    r = compute_cutback_frequency(11, passes, []).value
    assert r.cutbacks == 0


def test_per_match_normalization():
    passes = [_p(11, 92, 15, 87, 50)]
    r = compute_cutback_frequency(11, passes, [], matches_analyzed=2).value
    assert r.cutbacks_per_match == 0.5
