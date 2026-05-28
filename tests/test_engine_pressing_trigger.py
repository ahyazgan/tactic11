"""engine.pressing_trigger — gegenpress tetik süresi tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.pressing_trigger import (
    HIGH_PRESS_THRESHOLD_MIN,
    compute_pressing_trigger,
)


def _p(team: int, minute: float, completed: bool = True, period: int = 1) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=period,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def _d(team: int, minute: float, action_type: str = "ball_recovery",
       period: int = 1) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=2,
        team_external_id=team, minute=minute, period=period,
        x=50, y=50, action_type=action_type,  # type: ignore[arg-type]
    )


def test_gegenpress_fast_recovery_after_loss():
    """Bizim takım pas kaybediyor, 5 saniyede top tekrar bizde."""
    passes = [
        _p(team=11, minute=5.0, completed=False),  # bizim kayıp
    ]
    defs = [
        _d(team=11, minute=5.08, action_type="ball_recovery"),  # 5 sn sonra geri kazandık
    ]
    r = compute_pressing_trigger(11, passes, defs).value
    assert r.recoveries == 1
    assert r.fast_recoveries == 1
    assert r.fast_recovery_ratio == 1.0
    assert r.avg_recovery_time_min < HIGH_PRESS_THRESHOLD_MIN
    assert r.style_label == "gegenpress"


def test_low_block_slow_recovery():
    """Top kayıp + 30 saniye sonra kazanım → mid/low style."""
    passes = [_p(team=11, minute=5.0, completed=False)]
    defs = [_d(team=11, minute=5.50, action_type="tackle")]  # 30 sn sonra
    r = compute_pressing_trigger(11, passes, defs).value
    assert r.recoveries == 1
    assert r.fast_recoveries == 0
    assert r.style_label in ("mid_press", "low_block")


def test_no_recoveries_insufficient_data():
    r = compute_pressing_trigger(11, [], []).value
    assert r.recoveries == 0
    assert r.style_label == "insufficient_data"


def test_only_opponent_recoveries_ignored():
    passes = [_p(team=11, minute=5.0, completed=False)]
    defs = [_d(team=22, minute=5.05, action_type="ball_recovery")]  # rakip kazandı
    r = compute_pressing_trigger(11, passes, defs).value
    assert r.recoveries == 0


def test_multiple_recoveries_averaged():
    passes = [
        _p(team=11, minute=5.0, completed=False),
        _p(team=11, minute=20.0, completed=False),
    ]
    defs = [
        _d(team=11, minute=5.10, action_type="ball_recovery"),  # 6 sn
        _d(team=11, minute=20.50, action_type="tackle"),         # 30 sn
    ]
    r = compute_pressing_trigger(11, passes, defs).value
    assert r.recoveries == 2
    assert r.fast_recoveries == 1
    # Avg ~0.30 dk
    assert 0.20 <= r.avg_recovery_time_min <= 0.35


def test_audit_includes_threshold():
    r = compute_pressing_trigger(11, [], [])
    assert r.audit.engine == "engine.pressing_trigger"
    assert r.audit.inputs["high_press_threshold_min"] == HIGH_PRESS_THRESHOLD_MIN
