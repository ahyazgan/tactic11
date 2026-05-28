"""engine.field_tilt tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.field_tilt import FINAL_THIRD_X_MIN, compute_field_tilt


def _pass(team_id: int, end_x: float, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=1, team_external_id=team_id,
        minute=10.0, period=1,
        start_x=50.0, start_y=50.0, end_x=end_x, end_y=50.0,
        completed=completed,
    )


def test_dominant_team_has_high_tilt():
    """Team A 10, Team B 2 final-third pasları → A tilt > 0.8."""
    passes = [_pass(1, end_x=80.0) for _ in range(10)]
    passes += [_pass(2, end_x=80.0) for _ in range(2)]
    r = compute_field_tilt(1, 2, passes)
    assert r.value.team_a_tilt > 0.8
    assert r.value.team_b_tilt < 0.2
    assert abs(r.value.team_a_tilt + r.value.team_b_tilt - 1.0) < 1e-4


def test_equal_passes_means_50_50():
    passes = [_pass(1, end_x=70.0) for _ in range(5)]
    passes += [_pass(2, end_x=70.0) for _ in range(5)]
    r = compute_field_tilt(1, 2, passes)
    assert abs(r.value.team_a_tilt - 0.5) < 1e-4


def test_excludes_incomplete_passes():
    """Tamamlanmamış paslar field tilt'e girmez."""
    passes = [
        _pass(1, end_x=80.0, completed=True),
        _pass(1, end_x=80.0, completed=False),  # sayılmaz
        _pass(2, end_x=80.0, completed=True),
    ]
    r = compute_field_tilt(1, 2, passes)
    assert r.value.team_a_passes_in_a_final_third == 1
    assert r.value.team_b_passes_in_b_final_third == 1


def test_excludes_passes_before_final_third():
    """End_x < 66 olan paslar (final third dışı) sayılmaz."""
    passes = [
        _pass(1, end_x=50.0),  # final third'den önce
        _pass(1, end_x=80.0),  # final third içinde
    ]
    r = compute_field_tilt(1, 2, passes)
    assert r.value.team_a_passes_in_a_final_third == 1


def test_other_teams_excluded():
    """Sadece a/b teams sayılır, üçüncü takım sayılmaz."""
    passes = [
        _pass(1, end_x=80.0),
        _pass(2, end_x=80.0),
        _pass(99, end_x=80.0),  # üçüncü takım — yok sayılır
    ]
    r = compute_field_tilt(1, 2, passes)
    assert r.value.team_a_passes_in_a_final_third == 1
    assert r.value.team_b_passes_in_b_final_third == 1


def test_no_passes_defaults_to_50_50():
    r = compute_field_tilt(1, 2, [])
    assert r.value.team_a_tilt == 0.5
    assert r.value.team_b_tilt == 0.5


def test_audit_records_threshold():
    r = compute_field_tilt(1, 2, [])
    assert r.audit.engine == "engine.field_tilt"
    assert r.audit.inputs["final_third_x_min"] == FINAL_THIRD_X_MIN
