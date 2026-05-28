"""engine.transition — top kazanım → şut conversion tests.

v2: recovery_to_shot_conversion ana metrik. Eski fast_counter_ratio
backward-compat için tutuluyor ama style_label yeni metric'ten.
"""

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
    assert r.total_recoveries == 1
    assert r.fast_counter_attacks == 1
    assert r.avg_time_to_shot_min < FAST_COUNTER_MAX_MIN
    assert r.recovery_to_shot_conversion == 1.0


def test_slow_buildup_outside_window():
    """Kazanım 20.0; şut 21.0 (1 dakika sonra) → pencere dışı."""
    defs = [_d(11, 20.0)]
    shots = [_s(21.0)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 0
    assert r.recovery_to_shot_conversion == 0.0


def test_counter_attacking_style_high_conversion():
    """5 kazanımdan 5'i şuta → conversion 100%, counter_attacking."""
    defs = [_d(11, 10.0), _d(11, 30.0), _d(11, 50.0), _d(11, 65.0), _d(11, 70.0)]
    shots = [_s(10.10), _s(30.05), _s(50.10), _s(65.08), _s(70.05)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 5
    assert r.recovery_to_shot_conversion >= 0.03
    assert r.style_label == "counter_attacking"


def test_possession_style_low_conversion():
    """10 kazanımdan 0'ı şuta → conversion 0%, possession.

    La Liga audit: gerçek conversion %1-5; bu test 0% olduğu için
    açık seçik possession.
    """
    # 10 recovery, hiçbiri yeterince hızlı şuta dönüşmüyor
    defs = [_d(11, float(i)) for i in range(10, 81, 7)]
    # Şutlar 1 dk sonra (pencere dışı)
    shots = [_s(float(i + 1.0)) for i in range(10, 81, 7)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 0
    assert r.style_label == "possession"


def test_insufficient_data():
    r = compute_transition(11, [], []).value
    assert r.style_label == "insufficient_data"


def test_insufficient_total_recoveries():
    """< 5 recovery → insufficient (yeni v2 eşik)."""
    defs = [_d(11, 10.0)]
    shots = [_s(10.10)]
    r = compute_transition(11, defs, shots).value
    assert r.style_label == "insufficient_data"


def test_opponent_recovery_ignored():
    defs = [_d(22, 20.0)]  # rakip kazandı
    shots = [_s(20.10)]
    r = compute_transition(11, defs, shots).value
    assert r.recoveries_with_shot == 0
    assert r.total_recoveries == 0


def test_transitions_per_match_normalized():
    """matches_analyzed=2 → rec_w_shot / 2."""
    defs = [_d(11, float(i)) for i in range(10, 65, 10)]
    shots = [_s(float(i + 0.05)) for i in range(10, 65, 10)]
    r = compute_transition(11, defs, shots, matches_analyzed=2).value
    assert r.transitions_per_match == round(r.recoveries_with_shot / 2, 2)
