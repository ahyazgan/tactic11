"""engine.recovery_zone_heat tests."""

from __future__ import annotations

from app.domain import DefensiveAction
from app.engine.recovery_zone_heat import compute_recovery_zone_heat


def _d(team: int, x: float, action: str = "ball_recovery") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        x=x, y=50, action_type=action,  # type: ignore[arg-type]
    )


def test_high_press_style():
    """%50+ attacking third recovery → high_press."""
    defs = [_d(11, 75) for _ in range(6)] + [_d(11, 30)] * 2
    r = compute_recovery_zone_heat(11, defs).value
    assert r.attacking_share >= 0.50
    assert r.style_label == "high_press"


def test_deep_block_style():
    defs = [_d(11, 20) for _ in range(6)] + [_d(11, 40)] * 2
    r = compute_recovery_zone_heat(11, defs).value
    assert r.defensive_share >= 0.50
    assert r.style_label == "deep_block"


def test_mid_press_style():
    defs = [_d(11, 40) for _ in range(5)] + [_d(11, 30), _d(11, 75)]
    r = compute_recovery_zone_heat(11, defs).value
    assert r.style_label == "mid_press"


def test_only_recovery_actions_counted():
    """pressure recovery değil — sayılmaz."""
    defs = [_d(11, 75, action="pressure")]
    r = compute_recovery_zone_heat(11, defs).value
    assert r.total_recoveries == 0


def test_insufficient_data():
    r = compute_recovery_zone_heat(11, []).value
    assert r.style_label == "insufficient_data"
