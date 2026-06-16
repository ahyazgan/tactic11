"""C anomaly + E development_curve — saf zeka engine'leri."""
from __future__ import annotations

from app.engine.anomaly import detect_anomalies
from app.engine.development_curve import development_curve

# --------------------------------------------------------------------------- #
# C — anomaly
# --------------------------------------------------------------------------- #


def test_anomaly_detects_spike():
    series = [1.0, 1.1, 0.9, 1.0, 5.0, 1.0, 0.95]
    r = detect_anomalies(series)
    assert any(a.index == 4 and a.direction == "yüksek" for a in r.anomalies)


def test_anomaly_no_false_positive_on_flat():
    series = [1.0, 1.0, 1.0, 1.0, 1.0]
    r = detect_anomalies(series)
    assert r.anomalies == ()


def test_form_break_downward():
    # önceki pencere yüksek, son pencere düşük → düşüş kırılması
    series = [2.0, 2.1, 2.0, 0.5, 0.4, 0.6]
    r = detect_anomalies(series)
    assert r.break_detected is True
    assert r.break_direction == "düşüş"


def test_anomaly_short_series_safe():
    r = detect_anomalies([1.0])
    assert r.n == 1
    assert r.anomalies == ()


# --------------------------------------------------------------------------- #
# E — development_curve
# --------------------------------------------------------------------------- #


def test_curve_rising_trend():
    r = development_curve([0.2, 0.4, 0.6, 0.8, 1.0])
    assert r.direction == "yükseliş"
    assert r.slope > 0
    assert r.projection_next > 1.0


def test_curve_falling_trend():
    r = development_curve([1.0, 0.8, 0.6, 0.4, 0.2])
    assert r.direction == "düşüş"
    assert r.slope < 0


def test_curve_flat_trend():
    r = development_curve([0.5, 0.51, 0.49, 0.5, 0.5])
    assert r.direction == "sabit"


def test_curve_empty_and_single_safe():
    assert development_curve([]).n == 0
    one = development_curve([0.7])
    assert one.n == 1
    assert one.projection_next == 0.7
