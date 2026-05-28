"""engine.transition — top kazanım → şut süresi tests."""

from __future__ import annotations

from app.domain import DefensiveAction, Shot
from app.engine.transition import (
    FAST_COUNTER_MAX_MIN,
    compute_transition,
)


def _d(team: int, minute: float, action: str = "ball_recovery") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        x=40, y=50, action_type=action,  # type: ignore[arg-type]
    )


def _s(minute: float, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=90, y=50, is_goal=is_goal,
    )


def test_fast_counter_under_10s():
    """Top kazanım 20.0; şut 20.10 (6 sn) → fast counter."""
    defs = [_d(11, 20.0)]
    shots = [_s(20.10)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 1
    assert r.fast_counter_attacks == 1
    assert r.avg_time_to_shot_min < FAST_COUNTER_MAX_MIN


def test_slow_buildup_outside_window():
    """Kazanım 20.0; şut 21.0 (1 dakika sonra) → pencere dışı."""
    defs = [_d(11, 20.0)]
    shots = [_s(21.0)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 0


def test_counter_attacking_style():
    """Çoğu kazanım hızlı şuta dönüyor → counter_attacking style."""
    defs = [_d(11, 10.0), _d(11, 30.0), _d(11, 50.0)]
    shots = [_s(10.10), _s(30.05), _s(50.10)]
    r = compute_transition(11, defs, shots).value
    assert r.fast_counter_attacks == 3
    assert r.style_label == "counter_attacking"


def test_possession_style_no_fast_counters():
    """Hiç hızlı kontra yok → possession (3+ recovery şartıyla)."""
    defs = [_d(11, 10.0), _d(11, 30.0), _d(11, 50.0)]
    # Şutlar 20 saniye sonra (yavaş)
    shots = [_s(10.22), _s(30.20), _s(50.22)]
    r = compute_transition(11, defs, shots).value
    assert r.fast_counter_attacks == 0
    assert r.style_label in ("balanced", "possession")


def test_insufficient_data():
    r = compute_transition(11, [], []).value
    assert r.style_label == "insufficient_data"


def test_opponent_recovery_ignored():
    defs = [_d(22, 20.0)]  # rakip kazandı
    shots = [_s(20.10)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 0
