"""engine.defensive_line — savunma hattı yüksekliği tests."""

from __future__ import annotations

from app.domain import DefensiveAction
from app.engine.defensive_line import compute_defensive_line


def _d(team: int, x: float, action_type: str = "tackle") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        x=x, y=50, action_type=action_type,  # type: ignore[arg-type]
    )


def test_high_line():
    """Ortalama x ≥ 50 → high block."""
    defs = [_d(11, 55), _d(11, 60), _d(11, 50), _d(11, 65)]
    r = compute_defensive_line(11, defs).value
    assert r.line_label == "high"
    assert r.avg_x >= 50.0


def test_low_block():
    """Ortalama x < 35 → low block."""
    defs = [_d(11, 25), _d(11, 30), _d(11, 20)]
    r = compute_defensive_line(11, defs).value
    assert r.line_label == "low"
    assert r.avg_x < 35


def test_mid_line():
    defs = [_d(11, 38), _d(11, 42), _d(11, 40)]
    r = compute_defensive_line(11, defs).value
    assert r.line_label == "mid"


def test_pressure_excluded():
    """Pressure aksiyonları line height hesabına dahil değil."""
    defs = [
        _d(11, 20, "tackle"),
        _d(11, 80, "pressure"),  # ignore edilmeli
    ]
    r = compute_defensive_line(11, defs).value
    assert r.actions_counted == 1
    assert r.avg_x == 20.0


def test_opponent_actions_ignored():
    defs = [_d(11, 30, "tackle"), _d(22, 80, "tackle")]
    r = compute_defensive_line(11, defs).value
    assert r.actions_counted == 1


def test_empty_insufficient_data():
    r = compute_defensive_line(11, []).value
    assert r.line_label == "insufficient_data"


def test_percentiles_consistent():
    defs = [_d(11, x) for x in [10, 20, 30, 40, 50]]
    r = compute_defensive_line(11, defs).value
    assert r.p25_x < r.median_x < r.p75_x
    assert r.median_x == 30.0
