"""engine.press_resistance — pres altında pas tamamlama tests."""

from __future__ import annotations

import pytest

from app.domain import DefensiveAction, PassEvent
from app.engine.press_resistance import compute_press_resistance


def _p(team: int, player: int, sx: float, sy: float, minute: float = 10.0,
       completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=sx + 5, end_y=sy,
        completed=completed,
    )


def _pressure(team: int, x: float, y: float, minute: float = 10.0) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=99,
        team_external_id=team, minute=minute, period=1,
        x=x, y=y, action_type="pressure",
    )


def test_team_high_press_resistance():
    """Pres altında %80 pas tamamlama → yüksek resistance."""
    passes = [
        _p(11, 1, 50, 50, completed=True),
        _p(11, 1, 50, 50, completed=True),
        _p(11, 1, 50, 50, completed=True),
        _p(11, 1, 50, 50, completed=True),
        _p(11, 1, 50, 50, completed=False),  # 4/5 = 0.80
    ]
    # 5 rakip pressure yakın
    pressures = [_pressure(22, 52, 50) for _ in range(5)]
    r = compute_press_resistance(
        team_external_id=11, all_passes=passes, all_def_actions=pressures,
    ).value
    assert r.passes_under_press == 5
    assert r.completion_rate_under_press == 0.8


def test_player_subject():
    """Sadece bir oyuncuya filtrele."""
    passes = [
        _p(11, 100, 50, 50, completed=True),
        _p(11, 100, 50, 50, completed=True),
        _p(11, 200, 50, 50, completed=False),  # farklı oyuncu
    ]
    pressures = [_pressure(22, 52, 50)]
    r = compute_press_resistance(
        player_external_id=100, all_passes=passes, all_def_actions=pressures,
    ).value
    assert r.player_external_id == 100
    assert r.passes_under_press == 2
    assert r.completion_rate_under_press == 1.0


def test_no_subject_raises():
    with pytest.raises(ValueError, match="verilmeli"):
        compute_press_resistance(all_passes=[], all_def_actions=[])


def test_distant_pressure_not_counted():
    """Pressure çok uzakta (>8 birim) → pres altında değil."""
    passes = [_p(11, 1, 50, 50, completed=True)]
    pressures = [_pressure(22, 70, 50)]  # 20 birim uzakta
    r = compute_press_resistance(
        team_external_id=11, all_passes=passes, all_def_actions=pressures,
    ).value
    assert r.passes_under_press == 0
    assert r.completion_rate_unpressed == 1.0


def test_delta_positive_when_resistant():
    """Pres altı 80% + serbest 90% → delta -0.1 (normal kayıp)."""
    passes = (
        # pres altında 5 pas, 4 tamamlandı
        [_p(11, 1, 50, 50, minute=10.0, completed=True) for _ in range(4)] +
        [_p(11, 1, 50, 50, minute=10.0, completed=False)] +
        # presiz 10 pas, 9 tamamlandı
        [_p(11, 1, 80, 50, minute=20.0, completed=True) for _ in range(9)] +
        [_p(11, 1, 80, 50, minute=20.0, completed=False)]
    )
    pressures = [_pressure(22, 52, 50, minute=10.0)]
    r = compute_press_resistance(
        team_external_id=11, all_passes=passes, all_def_actions=pressures,
    ).value
    assert r.passes_under_press == 5
    assert r.completion_rate_under_press == 0.8
    assert r.completion_rate_unpressed == 0.9
    assert r.press_resistance_delta == round(0.8 - 0.9, 3)


def test_own_team_pressure_ignored():
    """Bizim takımın pressure eventi (anormal) yine de bizden değil; filtre düz."""
    passes = [_p(11, 1, 50, 50, completed=True)]
    pressures = [_pressure(11, 52, 50)]  # bizim takım pressure (olmaz ama yine de)
    r = compute_press_resistance(
        team_external_id=11, all_passes=passes, all_def_actions=pressures,
    ).value
    # Bizim takımın pressure'ı rakip değil → press_resistance filter dışı
    assert r.passes_under_press == 0
