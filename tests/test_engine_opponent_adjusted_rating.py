"""Opponent-Strength Adjusted Rating testleri."""
from __future__ import annotations

from app.engine.opponent_adjusted_rating import (
    PerformanceVsOpponent,
    compute_opponent_adjusted_rating,
)


def _p(pid, rating, opp_rating):
    return PerformanceVsOpponent(
        match_id=pid, rating=rating, opp_rating=opp_rating,
    )


def test_tough_opponent_gets_boost():
    """7.5 vs 8.5 (tough) → adjusted yukarı."""
    samples = [_p(1, 7.5, 8.5)]
    r = compute_opponent_adjusted_rating(
        samples, beta=0.30, league_avg=7.0,
    ).value
    s = r.samples[0]
    # adjusted = 7.5 + 0.30 * (8.5 - 7.0) = 7.5 + 0.45 = 7.95
    assert s.adjusted > s.raw
    assert abs(s.adjusted - 7.95) < 0.01
    assert s.bucket == "tough"


def test_easy_opponent_gets_penalty():
    samples = [_p(1, 8.0, 5.0)]
    r = compute_opponent_adjusted_rating(
        samples, beta=0.30, league_avg=7.0,
    ).value
    s = r.samples[0]
    # adjusted = 8.0 + 0.30 * (5.0 - 7.0) = 8.0 - 0.60 = 7.40
    assert s.adjusted < s.raw
    assert abs(s.adjusted - 7.40) < 0.01
    assert s.bucket == "easy"


def test_average_opponent_no_change():
    samples = [_p(1, 7.0, 7.0)]
    r = compute_opponent_adjusted_rating(
        samples, beta=0.30, league_avg=7.0,
    ).value
    s = r.samples[0]
    assert abs(s.adjusted - s.raw) < 0.01
    assert s.bucket == "average"


def test_bucket_thresholds():
    samples = [
        _p(1, 7.0, 5.0),   # easy
        _p(2, 7.0, 7.0),   # average
        _p(3, 7.0, 8.0),   # tough
    ]
    r = compute_opponent_adjusted_rating(samples).value
    bucket_names = {b.name for b in r.buckets}
    assert {"easy", "average", "tough"}.issubset(bucket_names)


def test_clamped_to_0_10():
    samples = [_p(1, 9.5, 10.0)]
    r = compute_opponent_adjusted_rating(
        samples, beta=2.0, league_avg=5.0,
    ).value
    # 9.5 + 2.0 * (10 - 5) = 19.5 → clamp to 10
    assert r.samples[0].adjusted == 10.0


def test_top_overperformance_match():
    samples = [
        _p(1, 5.0, 5.0),
        _p(2, 8.0, 9.0),   # over
        _p(3, 6.0, 6.0),
    ]
    r = compute_opponent_adjusted_rating(samples).value
    assert r.top_overperformance_match == 2


def test_top_underperformance_match():
    samples = [
        _p(1, 7.0, 7.0),
        _p(2, 7.0, 5.0),   # under (easy opp)
        _p(3, 7.0, 6.5),
    ]
    r = compute_opponent_adjusted_rating(samples).value
    assert r.top_underperformance_match == 2


def test_league_avg_defaults_to_series_mean():
    """league_avg verilmediğinde, opp_rating ortalaması kullanılır."""
    samples = [
        _p(1, 7.0, 6.0),
        _p(2, 7.0, 8.0),
    ]
    r = compute_opponent_adjusted_rating(samples).value
    assert r.league_avg_used == 7.0


def test_equal_opponents_no_adjustment_note():
    samples = [_p(1, 7.0, 7.0), _p(2, 7.5, 7.0), _p(3, 6.5, 7.0)]
    r = compute_opponent_adjusted_rating(samples).value
    assert any("eşit güçte" in n.lower() for n in r.notes)


def test_adjusted_mean_above_raw_when_mostly_tough():
    samples = [
        _p(1, 7.0, 8.5),
        _p(2, 7.5, 8.0),
        _p(3, 7.0, 7.8),
    ]
    r = compute_opponent_adjusted_rating(
        samples, beta=0.30, league_avg=7.0,
    ).value
    assert r.adjusted_mean > r.raw_mean


def test_empty_samples():
    r = compute_opponent_adjusted_rating([]).value
    assert r.sample_count == 0


def test_audit_complete():
    samples = [_p(1, 7.0, 7.0), _p(2, 7.5, 8.0)]
    res = compute_opponent_adjusted_rating(samples)
    a = res.audit.value
    assert "raw_mean" in a
    assert "adjusted_mean" in a
    assert "delta_mean" in a
    assert "league_avg" in a
    assert "beta" in a


def test_bucket_means_correct():
    samples = [
        _p(1, 8.0, 5.0),    # easy
        _p(2, 6.0, 8.0),    # tough
        _p(3, 6.5, 8.2),    # tough
    ]
    r = compute_opponent_adjusted_rating(
        samples, beta=0.30, league_avg=7.0,
    ).value
    easy = next(b for b in r.buckets if b.name == "easy")
    tough = next(b for b in r.buckets if b.name == "tough")
    assert easy.n == 1
    assert tough.n == 2
    assert easy.raw_mean == 8.0
    assert tough.raw_mean == 6.25


def test_summary_includes_means():
    samples = [_p(1, 7.0, 7.0), _p(2, 7.5, 7.5)]
    r = compute_opponent_adjusted_rating(samples).value
    assert "raw mean" in r.summary.lower() or "Raw mean" in r.summary
    assert "adjusted mean" in r.summary.lower() or "Adjusted" in r.summary


def test_higher_beta_amplifies_adjustment():
    samples = [_p(1, 7.0, 9.0)]
    r_low = compute_opponent_adjusted_rating(
        samples, beta=0.1, league_avg=7.0,
    ).value
    r_high = compute_opponent_adjusted_rating(
        samples, beta=1.0, league_avg=7.0,
    ).value
    assert r_high.samples[0].adjusted > r_low.samples[0].adjusted
