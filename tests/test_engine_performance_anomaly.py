"""Performance Anomaly Detector testleri."""
from __future__ import annotations

from app.engine.performance_anomaly import (
    PerformancePoint,
    compute_performance_anomaly,
)


def _pts(values, minutes=None, fatigue=None):
    minutes = minutes or [90.0] * len(values)
    fatigue = fatigue or [None] * len(values)
    return [
        PerformancePoint(
            match_id=i + 1, rating=v,
            minute_played=m, fatigue_proxy=f,
        )
        for i, (v, m, f) in enumerate(zip(values, minutes, fatigue, strict=False))
    ]


def test_no_anomaly_when_consistent_baseline():
    """Tutarlı 7.x serisinde anomali yok."""
    r = compute_performance_anomaly(_pts([7.0, 7.1, 7.0, 7.2, 7.0, 7.1])).value
    assert r.overall_risk == "low"
    assert len(r.events) == 0


def test_sudden_drop_detected_when_last_below():
    """Baseline 7.5 sd 0.3, son maç 5.0 → z ≈ -8 → sudden_drop."""
    r = compute_performance_anomaly(
        _pts([7.5, 7.3, 7.7, 7.6, 7.5, 5.0]),
    ).value
    drops = [e for e in r.events if e.type == "sudden_drop"]
    assert drops
    assert drops[0].severity in ("medium", "high")


def test_extended_decline_3_consecutive_low():
    """3 ardışık maç baseline-1σ altında → extended_decline."""
    r = compute_performance_anomaly(
        _pts([8.0, 7.8, 7.9, 6.0, 6.1, 6.2]),
    ).value
    declines = [e for e in r.events if e.type == "extended_decline"]
    assert declines


def test_minutes_drop_detected():
    """Son maç 20 dk vs baseline 90 dk → minutes_drop."""
    r = compute_performance_anomaly(
        _pts([7.0] * 6, minutes=[90, 90, 90, 90, 90, 20]),
    ).value
    drops = [e for e in r.events if e.type == "minutes_drop"]
    assert drops


def test_no_minutes_drop_when_normal_minutes():
    r = compute_performance_anomaly(
        _pts([7.0] * 6, minutes=[90, 90, 90, 90, 90, 85]),
    ).value
    drops = [e for e in r.events if e.type == "minutes_drop"]
    assert not drops


def test_consistency_collapse_when_recent_5_volatile():
    """İlk pencere tutarlı (CV düşük), son 5 maç çok volatil (CV yüksek)."""
    r = compute_performance_anomaly(
        _pts([7.0, 7.05, 6.95, 7.0, 7.0, 7.0, 3.0, 9.0, 4.0, 9.0, 3.0]),
    ).value
    collapses = [e for e in r.events if e.type == "consistency_collapse"]
    assert collapses


def test_fatigue_buildup_detected():
    """Son 3 fatigue ortalaması, tüm seriden +0.20 üstte."""
    r = compute_performance_anomaly(
        _pts(
            [7.0] * 8,
            fatigue=[0.3, 0.3, 0.3, 0.3, 0.3, 0.6, 0.7, 0.8],
        ),
    ).value
    fb = [e for e in r.events if e.type == "fatigue_buildup"]
    assert fb


def test_fatigue_buildup_skipped_when_no_proxy():
    """fatigue_proxy=None → fatigue_buildup hiç dedeklemez."""
    r = compute_performance_anomaly(_pts([7.0] * 8)).value
    fb = [e for e in r.events if e.type == "fatigue_buildup"]
    assert not fb


def test_insufficient_samples():
    r = compute_performance_anomaly(_pts([7.0, 7.5])).value
    assert "en az" in r.summary.lower()
    assert r.overall_risk == "low"


def test_empty_samples():
    r = compute_performance_anomaly([]).value
    assert r.sample_count == 0


def test_overall_risk_max_severity():
    """Birden çok anomali → en yüksek severity overall."""
    r = compute_performance_anomaly(
        _pts(
            [8.0, 7.9, 8.1, 4.5, 4.0, 3.5],  # extended decline + sudden drop
            minutes=[90, 90, 90, 90, 90, 15],
        ),
    ).value
    assert len(r.events) >= 2
    assert r.overall_risk in ("medium", "high")


def test_audit_complete():
    res = compute_performance_anomaly(_pts([7.0, 7.5, 7.0, 7.0, 7.0, 5.0]))
    a = res.audit.value
    assert "sample_count" in a
    assert "baseline_mean" in a
    assert "event_count" in a
    assert "event_types" in a
    assert "overall_risk" in a


def test_events_sorted_by_severity_then_confidence():
    r = compute_performance_anomaly(
        _pts(
            [8, 7.9, 8.1, 4.5, 4.0, 3.5],
            minutes=[90, 90, 90, 90, 90, 20],
        ),
    ).value
    if len(r.events) >= 2:
        sev_rank = {"low": 1, "medium": 2, "high": 3}
        ranks = [sev_rank[e.severity] for e in r.events]
        assert ranks == sorted(ranks, reverse=True)


def test_custom_k_sd_threshold():
    """Daha hassas threshold → daha çok event."""
    points = _pts([7.5, 7.5, 7.5, 7.5, 7.5, 7.0])
    r_default = compute_performance_anomaly(points, k_sd=1.5).value
    r_strict = compute_performance_anomaly(points, k_sd=0.5).value
    drops_default = [e for e in r_default.events if e.type == "sudden_drop"]
    drops_strict = [e for e in r_strict.events if e.type == "sudden_drop"]
    assert len(drops_strict) >= len(drops_default)


def test_summary_includes_worst_event():
    r = compute_performance_anomaly(
        _pts([7.5, 7.5, 7.5, 7.5, 7.5, 4.0]),
    ).value
    if r.events:
        assert r.events[0].type in r.summary
