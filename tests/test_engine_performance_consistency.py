"""Performance Consistency engine testleri."""
from __future__ import annotations

from app.engine.performance_consistency import (
    PerformanceSample,
    compute_performance_consistency,
)


def _samples(values):
    return [PerformanceSample(match_id=i + 1, value=v) for i, v in enumerate(values)]


def test_high_consistency_low_cv():
    """Tutarlı rating: 7.0, 7.1, 6.9, 7.0, 7.1 → CV < 0.10."""
    r = compute_performance_consistency(_samples([7.0, 7.1, 6.9, 7.0, 7.1])).value
    assert r.consistency_label == "high"
    assert r.cv < 0.10


def test_volatile_high_cv():
    """Çok değişken: 3, 8, 4, 9, 5 → CV ≥ 0.20."""
    r = compute_performance_consistency(_samples([3.0, 8.0, 4.0, 9.0, 5.0])).value
    assert r.consistency_label == "volatile"
    assert r.cv >= 0.20


def test_insufficient_when_lt_3_samples():
    r = compute_performance_consistency(_samples([7.0, 7.5])).value
    assert r.consistency_label == "insufficient"


def test_empty_samples():
    r = compute_performance_consistency([]).value
    assert r.sample_count == 0
    assert r.consistency_label == "insufficient"


def test_mean_sd_best_worst():
    r = compute_performance_consistency(_samples([6.0, 7.0, 8.0])).value
    assert r.mean == 7.0
    assert r.best == 8.0
    assert r.worst == 6.0
    assert r.sd > 0


def test_recent_5_z_positive_when_form_up():
    """Genel mean 5.0, son 5 mean 7.0 → z > 0."""
    values = [3, 4, 5, 5, 6, 7, 7, 7, 8, 6]  # son 5 = 7,7,7,8,6 mean 7.0
    r = compute_performance_consistency(_samples(values)).value
    assert r.z_recent_5 > 0.0


def test_recent_5_z_negative_when_form_down():
    """Genel iyiyim, son 5 düştü → z < 0."""
    values = [8, 8, 8, 8, 8, 5, 5, 5, 5, 5]
    r = compute_performance_consistency(_samples(values)).value
    assert r.z_recent_5 < 0.0


def test_reliability_score_high_for_consistent_high_rating():
    """Yüksek mean + düşük cv → yüksek reliability."""
    r = compute_performance_consistency(_samples([8.0] * 10)).value
    # cv ~ 0, mean 8 → ~80
    assert r.reliability_score >= 70.0


def test_reliability_score_low_for_low_mean():
    r = compute_performance_consistency(_samples([3.0] * 10)).value
    assert r.reliability_score <= 40.0


def test_audit_complete():
    res = compute_performance_consistency(_samples([7, 7, 7, 7]))
    a = res.audit.value
    assert "sample_count" in a
    assert "mean" in a
    assert "cv" in a
    assert "label" in a


def test_summary_mentions_label_when_sufficient():
    r = compute_performance_consistency(_samples([7.0] * 5)).value
    assert "high" in r.summary
    assert "mean" in r.summary.lower() or "Mean" in r.summary
