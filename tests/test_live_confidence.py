"""live_confidence — canlı güven skoru + zamansal trend (saf)."""
from __future__ import annotations

from app.engine.live_confidence import live_signal_confidence, summarize_trend

# --------------------------------------------------------------------------- #
# live_signal_confidence
# --------------------------------------------------------------------------- #


def test_early_minute_few_events_low():
    c = live_signal_confidence(events_so_far=20, current_minute=8.0)
    assert c.label == "düşük"


def test_late_minute_many_events_high():
    c = live_signal_confidence(events_so_far=900, current_minute=80.0)
    assert c.label == "yüksek"


def test_corroboration_lifts_confidence():
    base = live_signal_confidence(events_so_far=250, current_minute=45.0)
    boosted = live_signal_confidence(
        events_so_far=250, current_minute=45.0, corroborating_signals=3
    )
    assert boosted.score > base.score


def test_score_monotonic_in_events():
    low = live_signal_confidence(events_so_far=30, current_minute=40.0)
    high = live_signal_confidence(events_so_far=400, current_minute=40.0)
    assert high.score > low.score


def test_zero_events_not_crash_and_low():
    c = live_signal_confidence(events_so_far=0, current_minute=1.0)
    assert 0.0 <= c.score <= 1.0
    assert c.label == "düşük"


# --------------------------------------------------------------------------- #
# summarize_trend
# --------------------------------------------------------------------------- #


def test_trend_warming_up_when_too_few():
    out = summarize_trend([{"momentum_score": 0.1}, {"momentum_score": 0.2}])
    assert out["status"] == "warming_up"


def test_trend_momentum_toward_us():
    hist = [
        {"momentum_score": -0.1, "primary": "A"},
        {"momentum_score": 0.2, "primary": "A"},
        {"momentum_score": 0.5, "primary": "A"},
    ]
    out = summarize_trend(hist)
    assert out["status"] == "ok"
    assert out["momentum"]["direction"] == "bize doğru"
    assert out["momentum"]["delta"] > 0


def test_trend_momentum_toward_opponent_sustained():
    hist = [
        {"momentum_score": -0.3},
        {"momentum_score": -0.4},
        {"momentum_score": -0.6},
    ]
    out = summarize_trend(hist)
    assert out["momentum"]["direction"] == "rakibe doğru"
    assert out["momentum"]["sustained_snapshots"] == 3


def test_trend_field_tilt_increasing():
    hist = [
        {"momentum_score": 0.0, "field_tilt": 0.40},
        {"momentum_score": 0.0, "field_tilt": 0.55},
        {"momentum_score": 0.0, "field_tilt": 0.70},
    ]
    out = summarize_trend(hist)
    assert out["field_tilt"] == "artan"


def test_trend_stability_detects_repeated_primary():
    hist = [
        {"momentum_score": 0.0, "primary": "değiştir 8 no"},
        {"momentum_score": 0.0, "primary": "değiştir 8 no"},
        {"momentum_score": 0.0, "primary": "değiştir 8 no"},
    ]
    out = summarize_trend(hist)
    assert out["stability"]["stable"] is True
    assert out["stability"]["repeats"] == 3


def test_trend_noisy_primary_not_stable():
    hist = [
        {"momentum_score": 0.0, "primary": "A"},
        {"momentum_score": 0.0, "primary": "B"},
        {"momentum_score": 0.0, "primary": "C"},
    ]
    out = summarize_trend(hist)
    assert out["stability"]["stable"] is False
    assert out["stability"]["repeats"] == 1
