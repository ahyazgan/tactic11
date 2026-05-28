"""engine.build_up_pattern tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.build_up_pattern import (
    DEFENSIVE_THIRD_MAX,
    LONG_BALL_DISTANCE,
    compute_build_up_pattern,
)


def _pass(
    poss_id: int, start_x: float, end_x: float = 50.0,
    *, minute: float = 10.0, team_id: int = 1, period: int = 1,
    start_y: float = 50.0, end_y: float = 50.0,
) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=1, team_external_id=team_id,
        minute=minute, period=period,
        start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y,
        completed=True,
        possession_id=poss_id,
    )


def test_zone_categorization():
    """Pas başlangıç x'i defansif/orta/hücum üçtebir."""
    passes = [
        _pass(1, start_x=15),    # def
        _pass(2, start_x=50),    # mid
        _pass(3, start_x=80),    # att
    ]
    r = compute_build_up_pattern(1, passes, [])
    assert r.value.starts_in_defensive_third == 1
    assert r.value.starts_in_middle_third == 1
    assert r.value.starts_in_attacking_third == 1


def test_long_ball_detection():
    """Pas mesafesi ≥ 35 → long_ball."""
    passes = [
        _pass(1, start_x=20, end_x=70),  # uzun (50 birim)
        _pass(2, start_x=50, end_x=55),  # kısa (5 birim)
    ]
    r = compute_build_up_pattern(1, passes, [])
    assert r.value.long_balls_pct == 0.5


def test_avg_sequence_length():
    """Possession 1: 3 pas, possession 2: 2 pas → avg 2.5."""
    passes = [
        _pass(1, start_x=30, minute=10.0),
        _pass(1, start_x=40, minute=10.1),
        _pass(1, start_x=50, minute=10.2),
        _pass(2, start_x=60, minute=20.0),
        _pass(2, start_x=70, minute=20.1),
    ]
    r = compute_build_up_pattern(1, passes, [])
    assert r.value.total_sequences == 2
    assert r.value.avg_sequence_length == 2.5


def test_progression_per_sequence():
    """İlk pas start_x=20, son pas end_x=80 → progression 60."""
    passes = [
        _pass(1, start_x=20, end_x=40, minute=10.0),
        _pass(1, start_x=40, end_x=80, minute=10.2),
    ]
    r = compute_build_up_pattern(1, passes, [])
    # Progression: last.end_x (80) - first.start_x (20) = 60
    assert r.value.avg_progression_meters == 60.0


def test_excludes_other_teams():
    passes = [
        _pass(1, start_x=20, team_id=10),
        _pass(2, start_x=30, team_id=99),  # diğer takım — hariç
    ]
    r = compute_build_up_pattern(10, passes, [])
    assert r.value.total_sequences == 1


def test_excludes_passes_without_possession_id():
    """possession_id None olan paslar agregat'a girmez."""
    passes = [
        _pass(1, start_x=20),
        PassEvent(
            sport="football", match_external_id=1,
            player_external_id=1, team_external_id=1,
            minute=15.0, period=1,
            start_x=30.0, start_y=50.0, end_x=40.0, end_y=50.0,
            completed=True, possession_id=None,
        ),
    ]
    r = compute_build_up_pattern(1, passes, [])
    assert r.value.total_sequences == 1


def test_empty_inputs_zero_report():
    r = compute_build_up_pattern(1, [], [])
    assert r.value.total_sequences == 0
    assert r.value.long_balls_pct == 0.0


def test_audit_includes_thresholds():
    r = compute_build_up_pattern(1, [], [])
    assert r.audit.engine == "engine.build_up_pattern"
    assert r.audit.inputs["long_ball_distance"] == LONG_BALL_DISTANCE
    assert r.audit.inputs["defensive_third_max"] == DEFENSIVE_THIRD_MAX
