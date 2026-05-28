"""engine.ppda tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.ppda import PRESS_ZONE_X_MIN, compute_ppda


def _pass(team_id: int, sx: float) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=1, team_external_id=team_id,
        minute=10.0, period=1,
        start_x=sx, start_y=50.0, end_x=sx + 5, end_y=50.0,
        completed=True,
    )


def _def_action(team_id: int, x: float, action_type: str = "tackle") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=1,
        player_external_id=2, team_external_id=team_id,
        minute=10.0, period=1,
        x=x, y=50.0,
        action_type=action_type,  # type: ignore[arg-type]
    )


def test_high_press_team_has_low_ppda():
    """20 rakip pas + 5 takım defansif aksiyon = PPDA 4 (yoğun pres)."""
    passes = [_pass(99, sx=60.0) for _ in range(20)]  # rakip pasları hücum yarısında
    actions = [_def_action(1, x=70.0) for _ in range(5)]  # bizim defansif aksiyonlar
    r = compute_ppda(1, passes, actions, matches_analyzed=1)
    assert r.value.ppda == 4.0
    assert r.value.opp_passes_in_press_zone == 20
    assert r.value.team_def_actions_in_press_zone == 5


def test_low_press_team_has_high_ppda():
    """20 rakip pas + 2 takım aksiyon = PPDA 10."""
    passes = [_pass(99, sx=60.0) for _ in range(20)]
    actions = [_def_action(1, x=70.0) for _ in range(2)]
    r = compute_ppda(1, passes, actions, matches_analyzed=1)
    assert r.value.ppda == 10.0


def test_excludes_passes_in_defensive_zone():
    """Rakibin defansif yarısında yaptığı paslar sayılmaz."""
    passes = [
        _pass(99, sx=20.0),  # defansif yarısında (< 40) — sayılmaz
        _pass(99, sx=50.0),  # press zone'da — sayılır
        _pass(99, sx=70.0),  # press zone'da — sayılır
    ]
    actions = [_def_action(1, x=60.0)]
    r = compute_ppda(1, passes, actions, matches_analyzed=1)
    assert r.value.opp_passes_in_press_zone == 2


def test_excludes_our_own_passes():
    """Bizim paslar değil, rakibin paslarını sayıyoruz."""
    passes = [
        _pass(1, sx=60.0),   # bizim (team_id=1) — sayılmaz
        _pass(99, sx=60.0),  # rakip — sayılır
    ]
    actions = [_def_action(1, x=60.0)]
    r = compute_ppda(1, passes, actions, matches_analyzed=1)
    assert r.value.opp_passes_in_press_zone == 1


def test_excludes_def_actions_in_our_defensive_zone():
    """Bizim defansif yarımızdaki aksiyonlar sayılmaz."""
    passes = [_pass(99, sx=60.0)]
    actions = [
        _def_action(1, x=30.0),  # bizim yarıda — sayılmaz
        _def_action(1, x=70.0),  # press zone — sayılır
    ]
    r = compute_ppda(1, passes, actions, matches_analyzed=1)
    assert r.value.team_def_actions_in_press_zone == 1


def test_zero_def_actions_returns_high_ppda():
    """Defansif aksiyon yoksa PPDA çok yüksek (sentinel 999)."""
    passes = [_pass(99, sx=60.0)]
    r = compute_ppda(1, passes, [], matches_analyzed=1)
    assert r.value.ppda == 999.0


def test_audit_records_press_zone_threshold():
    r = compute_ppda(1, [], [], matches_analyzed=1)
    assert r.audit.engine == "engine.ppda"
    assert r.audit.inputs["press_zone_x_min"] == PRESS_ZONE_X_MIN
