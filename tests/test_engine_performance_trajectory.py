"""Performance Trajectory engine testleri."""
from __future__ import annotations

from app.engine.performance_trajectory import (
    TrajectoryPoint,
    compute_performance_trajectory,
)


def _series(values):
    return [
        TrajectoryPoint(match_id=i + 1, value=v, game_index=i)
        for i, v in enumerate(values)
    ]


def test_improving_when_values_rise():
    r = compute_performance_trajectory(
        _series([5.0, 5.5, 6.0, 6.5, 7.0, 7.5]),
    ).value
    assert r.direction == "improving"
    assert r.slope > 0


def test_declining_when_values_fall():
    r = compute_performance_trajectory(
        _series([8.0, 7.5, 7.0, 6.5, 6.0, 5.5]),
    ).value
    assert r.direction == "declining"
    assert r.slope < 0


def test_stable_when_flat():
    r = compute_performance_trajectory(
        _series([7.0, 7.05, 6.95, 7.0, 7.0, 7.02]),
    ).value
    assert r.direction == "stable"
    assert abs(r.slope) < 0.05


def test_peak_and_dip_indices():
    r = compute_performance_trajectory(
        _series([6.0, 7.0, 9.0, 5.0, 7.0]),
    ).value
    assert r.peak_index == 2  # value 9.0
    assert r.dip_index == 3   # value 5.0


def test_projection_continues_slope():
    r = compute_performance_trajectory(_series([5.0, 6.0, 7.0, 8.0])).value
    # slope ~1, last value 8 → next ~9, 10, 11
    assert r.projection_next_3[0] > 8.0
    assert r.projection_next_3[2] > r.projection_next_3[0]


def test_insufficient_when_lt_2():
    r = compute_performance_trajectory(_series([7.0])).value
    assert r.direction == "insufficient"


def test_empty():
    r = compute_performance_trajectory([]).value
    assert r.sample_count == 0
    assert r.direction == "insufficient"


def test_smoothed_series_length_matches():
    r = compute_performance_trajectory(_series([6, 7, 8, 7, 6])).value
    assert len(r.smoothed_series) == 5


def test_rtm_warning_when_last_5_high():
    r = compute_performance_trajectory(_series([7, 7, 8.8, 8.9, 9.0, 8.8, 9.1])).value
    assert r.rtm_warning is not None
    assert "yüksek" in r.rtm_warning.lower() or "regression" in r.rtm_warning.lower()


def test_rtm_warning_when_last_5_low():
    r = compute_performance_trajectory(_series([7, 7, 5.2, 5.1, 5.0, 5.2, 5.0])).value
    assert r.rtm_warning is not None
    assert "düşük" in r.rtm_warning.lower()


def test_confidence_high_for_clean_trend():
    """Çok düzenli artış → conf yüksek."""
    r = compute_performance_trajectory(_series([5, 6, 7, 8, 9])).value
    assert r.confidence >= 0.8


def test_confidence_low_for_noisy_data():
    """Gürültülü → conf düşük."""
    r = compute_performance_trajectory(_series([7, 3, 9, 2, 8, 4, 7, 5])).value
    assert r.confidence < 0.5


def test_audit_complete():
    res = compute_performance_trajectory(_series([5, 6, 7]))
    a = res.audit.value
    assert "slope" in a
    assert "direction" in a
    assert "confidence" in a
    assert "peak_index" in a


def test_summary_includes_direction_and_slope():
    r = compute_performance_trajectory(_series([5, 6, 7, 8])).value
    assert r.direction in r.summary
    assert "slope" in r.summary.lower()
