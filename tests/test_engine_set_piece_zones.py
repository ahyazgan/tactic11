"""engine.set_piece_zones — duran top bölge ısı haritası tests."""

from __future__ import annotations

import pytest

from app.domain import Shot
from app.engine.set_piece_zones import compute_set_piece_zones


def _shot(x: float, y: float, pattern: str = "corner_kick",
          is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=1,
        minute=10.0, x=x, y=y, pattern=pattern,  # type: ignore[arg-type]
        is_goal=is_goal,
    )


def test_central_6yd_zone_dominant():
    shots = [
        _shot(96, 50, is_goal=True),
        _shot(96, 55, is_goal=True),
        _shot(95, 45, is_goal=False),
    ]
    r = compute_set_piece_zones(11, shots).value
    assert r.total_shots == 3
    assert r.total_goals == 2
    central = next(z for z in r.zones if z.zone == "central_6yd")
    assert central.shots == 3


def test_near_post_zone():
    shots = [_shot(92, 20, is_goal=True)]
    r = compute_set_piece_zones(11, shots).value
    near = next(z for z in r.zones if z.zone == "near_post")
    assert near.shots == 1
    assert r.most_threatening_zone == "near_post"


def test_far_post_zone():
    shots = [_shot(92, 80, is_goal=True), _shot(93, 75, is_goal=False)]
    r = compute_set_piece_zones(11, shots).value
    far = next(z for z in r.zones if z.zone == "far_post")
    assert far.shots == 2


def test_outside_box_zone():
    shots = [_shot(75, 50, is_goal=False)]
    r = compute_set_piece_zones(11, shots).value
    outside = next(z for z in r.zones if z.zone == "outside_box")
    assert outside.shots == 1


def test_penalty_arc_zone():
    shots = [_shot(85, 50, is_goal=False)]
    r = compute_set_piece_zones(11, shots).value
    arc = next(z for z in r.zones if z.zone == "penalty_arc")
    assert arc.shots == 1


def test_open_play_excluded():
    """Open-play shot atılır."""
    shots = [_shot(95, 50, pattern="open_play")]
    r = compute_set_piece_zones(11, shots).value
    assert r.total_shots == 0


def test_set_piece_type_filter():
    shots = [
        _shot(95, 50, pattern="corner_kick"),
        _shot(95, 50, pattern="free_kick"),
    ]
    r = compute_set_piece_zones(11, shots, set_piece_type="corner_kick").value
    assert r.total_shots == 1


def test_invalid_role_raises():
    with pytest.raises(ValueError, match="role"):
        compute_set_piece_zones(11, [], role="weird")


def test_most_threatening_picks_highest_conversion():
    shots = [
        _shot(96, 50, is_goal=True),
        _shot(96, 50, is_goal=True),    # central 2/2 = 1.00
        _shot(92, 20, is_goal=False),   # near_post 0/1 = 0.00
    ]
    r = compute_set_piece_zones(11, shots).value
    assert r.most_threatening_zone == "central_6yd"
