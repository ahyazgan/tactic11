"""Clutch Performance engine testleri."""
from __future__ import annotations

from app.engine.clutch_performance import (
    ClutchSample,
    compute_clutch_performance,
)


def _s(pid, rating, **flags):
    return ClutchSample(match_id=pid, rating=rating, flags=flags)


def test_clutch_player_high_factor():
    """Büyük maçlarda ortalamasının çok üstünde."""
    samples = [
        _s(1, 7.0),
        _s(2, 6.8),
        _s(3, 8.5, big_match=True),
        _s(4, 8.7, big_match=True),
        _s(5, 8.6, big_match=True),
        _s(6, 6.9),
    ]
    r = compute_clutch_performance(samples).value
    assert r.label == "clutch"
    assert r.clutch_factor >= 1.10
    assert r.strongest_clutch == "big_match"


def test_chokes_player_low_factor():
    """Büyük maçlarda ortalamasından çok daha kötü."""
    samples = [
        _s(1, 7.5),
        _s(2, 7.8),
        _s(3, 4.5, big_match=True),
        _s(4, 4.8, big_match=True),
        _s(5, 4.2, big_match=True),
    ]
    r = compute_clutch_performance(samples).value
    assert r.label == "chokes"
    assert r.clutch_factor < 0.95


def test_neutral_when_close_to_overall():
    samples = [
        _s(1, 7.0),
        _s(2, 7.1),
        _s(3, 7.05, close_game=True),
        _s(4, 7.0, close_game=True),
        _s(5, 7.15, close_game=True),
    ]
    r = compute_clutch_performance(samples).value
    assert r.label == "neutral"


def test_per_situation_breakdown_complete():
    samples = [
        _s(1, 7.0),
        _s(2, 7.2, close_game=True),
        _s(3, 7.5, big_match=True),
        _s(4, 7.8, big_match=True, close_game=True),
    ]
    r = compute_clutch_performance(samples).value
    dims = {b.dimension for b in r.per_situation}
    assert "big_match" in dims
    assert "close_game" in dims


def test_insufficient_when_few_clutch_samples():
    samples = [_s(1, 7.0), _s(2, 7.5), _s(3, 8.0, big_match=True)]
    r = compute_clutch_performance(samples).value
    assert r.label == "insufficient"
    assert any("yetersiz" in n.lower() or "kritik maç" in n.lower() for n in r.notes)


def test_no_flag_samples_returns_insufficient():
    samples = [_s(i, 7.0 + i * 0.05) for i in range(1, 6)]
    r = compute_clutch_performance(samples).value
    assert r.label == "insufficient"
    assert any("önem flag" in n.lower() for n in r.notes)


def test_insufficient_when_lt_2_samples():
    r = compute_clutch_performance([_s(1, 7.0)]).value
    assert r.sample_count == 1
    assert "en az" in r.summary.lower()


def test_empty_samples():
    r = compute_clutch_performance([]).value
    assert r.sample_count == 0


def test_strongest_clutch_picks_max_positive_delta():
    samples = [
        _s(1, 6.0),
        _s(2, 6.2),
        _s(3, 7.5, big_match=True),
        _s(4, 7.6, big_match=True),
        _s(5, 7.7, big_match=True),
        _s(6, 6.5, close_game=True),
        _s(7, 6.4, close_game=True),
    ]
    r = compute_clutch_performance(samples).value
    assert r.strongest_clutch == "big_match"


def test_weakest_clutch_picks_min_negative_delta():
    samples = [
        _s(1, 7.5), _s(2, 7.6),
        _s(3, 5.0, knockout=True),
        _s(4, 5.2, knockout=True),
        _s(5, 5.1, knockout=True),
    ]
    r = compute_clutch_performance(samples).value
    assert r.weakest_clutch == "knockout"


def test_multiple_flags_on_one_match():
    """Tek maç birden çok flag — her boyut breakdown'da görünür."""
    samples = [
        _s(1, 7.0),
        _s(2, 7.0),
        _s(3, 8.5, big_match=True, knockout=True, close_game=True),
        _s(4, 8.0, big_match=True),
    ]
    r = compute_clutch_performance(samples).value
    dims = {b.dimension for b in r.per_situation}
    assert {"big_match", "knockout", "close_game"}.issubset(dims)


def test_summary_includes_factor_and_label():
    samples = [
        _s(1, 7.0), _s(2, 7.2),
        _s(3, 8.5, big_match=True), _s(4, 8.4, big_match=True),
        _s(5, 8.6, big_match=True),
    ]
    r = compute_clutch_performance(samples).value
    assert "clutch" in r.summary.lower() or "factor" in r.summary.lower()


def test_audit_complete():
    samples = [
        _s(1, 6.0), _s(2, 6.5),
        _s(3, 8.5, big_match=True), _s(4, 8.6, big_match=True),
        _s(5, 8.7, big_match=True),
    ]
    res = compute_clutch_performance(samples)
    a = res.audit.value
    assert "sample_count" in a
    assert "clutch_factor" in a
    assert "label" in a
    assert "dimensions_with_data" in a
    assert a["label"] == "clutch"


def test_per_situation_factors_correct():
    """Per-situation factor = mean_in / mean_out."""
    samples = [
        _s(1, 6.0),         # not big_match
        _s(2, 6.0),
        _s(3, 9.0, big_match=True),
        _s(4, 9.0, big_match=True),
    ]
    r = compute_clutch_performance(samples).value
    bm = next(b for b in r.per_situation if b.dimension == "big_match")
    assert bm.mean_in == 9.0
    assert bm.mean_out == 6.0
    assert abs(bm.factor - 1.5) < 0.01


def test_per_situation_omits_dimensions_with_no_data():
    """Hiçbir maçta open olmayan dimension → per_situation'da yok."""
    samples = [
        _s(1, 7.0), _s(2, 7.0),
        _s(3, 8.0, big_match=True), _s(4, 8.0, big_match=True),
    ]
    r = compute_clutch_performance(samples).value
    dims = {b.dimension for b in r.per_situation}
    assert "big_match" in dims
    assert "knockout" not in dims  # bu maçlarda hiç set edilmedi
