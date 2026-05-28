"""engine.counter_press_triggers tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.counter_press_triggers import compute_counter_press_triggers


def _p(team: int, minute: float, completed: bool) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def _d(team: int, minute: float, action: str = "pressure") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        x=50, y=50, action_type=action,  # type: ignore[arg-type]
    )


def test_pressure_response_classified():
    """Pas kaybı 10.0; 4 sn sonra pressure → pressure response."""
    passes = [_p(11, 10.0, completed=False)]
    defs = [_d(11, 10.07, action="pressure")]
    r = compute_counter_press_triggers(11, passes, defs).value
    assert r.pressure_responses == 1
    assert r.dominant_trigger == "pressure"


def test_drop_back_no_response():
    """Pas kaybı; pencere içinde aksiyon yok → drop_back."""
    passes = [_p(11, 10.0, completed=False)]
    defs = [_d(11, 11.0, action="pressure")]  # 1 dk sonra, pencere dışı
    r = compute_counter_press_triggers(11, passes, defs).value
    assert r.no_response == 1
    assert r.dominant_trigger == "drop_back"


def test_tackle_response():
    passes = [_p(11, 10.0, completed=False)]
    defs = [_d(11, 10.05, action="tackle")]
    r = compute_counter_press_triggers(11, passes, defs).value
    assert r.tackle_responses == 1


def test_completed_pass_no_trigger():
    """Pas tamamlandı → kayıp yok → loss_analyzed=0."""
    passes = [_p(11, 10.0, completed=True)]
    defs = [_d(11, 10.05, action="pressure")]
    r = compute_counter_press_triggers(11, passes, defs).value
    assert r.losses_analyzed == 0


def test_dominant_when_pressure_majority():
    passes = [_p(11, 10.0, False), _p(11, 20.0, False), _p(11, 30.0, False)]
    defs = [
        _d(11, 10.05, action="pressure"),
        _d(11, 20.05, action="pressure"),
        _d(11, 30.05, action="tackle"),
    ]
    r = compute_counter_press_triggers(11, passes, defs).value
    assert r.dominant_trigger == "pressure"
