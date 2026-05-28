"""engine.fatigue_signal — yorulan oyuncu tespiti tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.fatigue_signal import compute_fatigue_signal


def _p(player: int, minute: float, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def _d(player: int, minute: float) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        x=50, y=50, action_type="tackle",
    )


def test_fresh_player_low_score():
    """Erken + geç hep tamamlanmış pas → fatigue düşük."""
    passes = (
        [_p(100, minute=5.0)] * 10 +
        [_p(100, minute=40.0)] * 10
    )
    r = compute_fatigue_signal(100, passes, []).value
    assert r.fatigue_score < 0.20
    assert r.recommendation == "fresh"


def test_urgent_fatigue_with_completion_drop():
    """Erken %100, geç %50 → urgent_sub."""
    passes = (
        [_p(100, minute=10.0, completed=True)] * 10 +
        [_p(100, minute=40.0, completed=True)] * 3 +
        [_p(100, minute=42.0, completed=False)] * 7
    )
    r = compute_fatigue_signal(100, passes, []).value
    assert r.early_pass_completion == 1.0
    assert r.late_pass_completion == 0.3
    assert r.fatigue_score >= 0.30


def test_action_count_drop():
    """Erken 20 aksiyon, geç 2 → büyük action drop."""
    passes = (
        [_p(100, minute=5.0)] * 20 +
        [_p(100, minute=40.0)] * 2
    )
    r = compute_fatigue_signal(100, passes, []).value
    assert r.action_count_drop_ratio > 0
    assert r.early_actions == 20
    assert r.late_actions == 2


def test_other_player_filtered():
    passes = [_p(200, minute=10.0)] * 10  # farklı oyuncu
    r = compute_fatigue_signal(100, passes, []).value
    assert r.early_actions == 0
    assert r.late_actions == 0
    assert r.recommendation == "insufficient_data"


def test_includes_defensive_actions_in_count():
    """Defensive aksiyonlar da action count'a girer."""
    passes = [_p(100, minute=5.0)] * 5
    defs = [_d(100, minute=5.0)] * 5
    r = compute_fatigue_signal(100, passes, defs).value
    assert r.early_actions == 10


def test_window_for_second_half():
    """2. yarı için custom window (45-90)."""
    passes = (
        [_p(100, minute=50.0, completed=True)] * 8 +
        [_p(100, minute=85.0, completed=False)] * 8
    )
    r = compute_fatigue_signal(
        100, passes, [],
        early_end=75.0, late_start=75.0,
        minutes_window=(45.0, 90.0),
    ).value
    assert r.early_actions == 8
    assert r.late_actions == 8
    assert r.fatigue_score >= 0.30  # complete drop'tan
