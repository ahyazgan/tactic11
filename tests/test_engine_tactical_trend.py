"""engine.tactical_trend — zaman serisi slope + direction tests."""

from __future__ import annotations

from app.engine.tactical_trend import compute_tactical_trend


def test_improving_higher_better():
    """Artan seri + higher_is_better=True → improving."""
    r = compute_tactical_trend("xg", [1.0, 1.5, 2.0, 2.5, 3.0],
                                higher_is_better=True).value
    assert r.direction == "improving"
    assert r.slope > 0


def test_improving_lower_better_ppda():
    """PPDA 15 → 10 (azalan, daha fazla pres) → higher_is_better=False → improving."""
    r = compute_tactical_trend("ppda", [15.0, 13.0, 11.0, 10.0],
                                higher_is_better=False).value
    assert r.slope < 0
    assert r.direction == "improving"


def test_worsening():
    r = compute_tactical_trend("xg", [3.0, 2.0, 1.0, 0.5],
                                higher_is_better=True).value
    assert r.direction == "worsening"


def test_stable_flat_series():
    """Düz seri → stable."""
    r = compute_tactical_trend("xg", [1.0, 1.0, 1.05, 1.0, 1.02],
                                higher_is_better=True).value
    assert r.direction == "stable"


def test_volatility_stdev():
    r = compute_tactical_trend("xg", [1.0, 5.0, 1.0, 5.0],
                                higher_is_better=True).value
    assert r.stdev > 0


def test_biggest_shift_detected():
    """En büyük ardışık fark + indekste."""
    r = compute_tactical_trend("xg", [1.0, 1.1, 5.0, 4.9],  # delta 3.9 @ idx=2
                                higher_is_better=True).value
    assert r.biggest_match_to_match_shift > 3.5
    assert r.biggest_shift_match_idx == 2


def test_empty_series_insufficient():
    r = compute_tactical_trend("xg", []).value
    assert r.direction == "insufficient_data"
    assert r.matches_analyzed == 0


def test_single_match_no_slope():
    r = compute_tactical_trend("xg", [2.0]).value
    assert r.matches_analyzed == 1
    assert r.slope == 0.0


def test_audit_includes_metric_name():
    r = compute_tactical_trend("ppda", [1.0, 2.0],
                                higher_is_better=False)
    assert r.audit.metric == "trend_ppda"
    assert r.audit.inputs["higher_is_better"] is False
