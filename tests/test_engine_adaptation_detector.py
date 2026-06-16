"""In-game adaptation detector testleri."""
from __future__ import annotations

from app.engine.adaptation_detector import SnapshotSample, compute_adaptation


def _snap(minute: float, **kwargs) -> SnapshotSample:
    base = dict(
        ppda_normalized=0.5, field_tilt_pct=0.5, press_height=0.5,
        direct_play_pct=0.3, counter_threat=0.4, high_line_risk=0.5,
    )
    base.update(kwargs)
    return SnapshotSample(minute=minute, **base)


def test_no_change_returns_empty_events():
    r = compute_adaptation([_snap(60), _snap(70), _snap(80)]).value
    assert len(r.events) == 0
    assert "anlamlı değişim yok" in r.summary


def test_press_drop_detected_60_to_75():
    samples = [
        _snap(60, ppda_normalized=0.85, press_height=0.85),
        _snap(75, ppda_normalized=0.50, press_height=0.55),
    ]
    r = compute_adaptation(samples).value
    assert len(r.events) >= 1
    # PPDA düştü → "rakip pres'i bıraktı"
    ppda_events = [e for e in r.events if e.dimension == "ppda_normalized"]
    assert ppda_events
    assert ppda_events[0].direction == "fell"
    assert "pres" in ppda_events[0].interpretation.lower()


def test_line_raised_detected():
    samples = [
        _snap(60, high_line_risk=0.30),
        _snap(75, high_line_risk=0.70),
    ]
    r = compute_adaptation(samples).value
    line_events = [e for e in r.events if e.dimension == "high_line_risk"]
    assert line_events
    assert line_events[0].direction == "rose"
    assert "dik koşu" in line_events[0].our_counter_advice.lower() or \
        "offside" in line_events[0].our_counter_advice.lower()


def test_field_tilt_increase_detected():
    samples = [
        _snap(60, field_tilt_pct=0.45),
        _snap(75, field_tilt_pct=0.65),
    ]
    r = compute_adaptation(samples).value
    tilt_events = [e for e in r.events if e.dimension == "field_tilt_pct"]
    assert tilt_events
    assert tilt_events[0].direction == "rose"


def test_significance_high_when_double_threshold():
    """Press_height 0.4 fark (eşik 0.15) → ratio 2.67 → high."""
    samples = [
        _snap(60, press_height=0.20),
        _snap(75, press_height=0.60),
    ]
    r = compute_adaptation(samples).value
    press_events = [e for e in r.events if e.dimension == "press_height"]
    assert press_events
    assert press_events[0].significance == "high"


def test_single_sample_returns_insufficient():
    r = compute_adaptation([_snap(60)]).value
    assert r.sample_count == 1
    assert "en az 2 snapshot" in r.summary


def test_empty_samples_insufficient():
    r = compute_adaptation([]).value
    assert r.sample_count == 0
    assert len(r.events) == 0


def test_custom_thresholds():
    """Custom (daha hassas) threshold → daha çok event."""
    samples = [
        _snap(60, ppda_normalized=0.50),
        _snap(75, ppda_normalized=0.40),  # 0.10 delta (default 0.15 yetersiz)
    ]
    r_default = compute_adaptation(samples).value
    r_strict = compute_adaptation(samples, thresholds={"ppda_normalized": 0.05}).value
    assert len(r_default.events) == 0
    assert len(r_strict.events) >= 1


def test_audit_complete():
    samples = [
        _snap(60, ppda_normalized=0.85),
        _snap(75, ppda_normalized=0.40),
    ]
    res = compute_adaptation(samples)
    a = res.audit.value
    assert "sample_count" in a
    assert "event_count" in a
    assert "dimensions_changed" in a
