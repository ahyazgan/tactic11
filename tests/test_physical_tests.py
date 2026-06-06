"""Fiziksel test modülü unit testleri — saf engine (DB/API gerekmez)."""

from app.engine.physical.load_risk import (
    compute_load_risk,
    compute_protocol_trend,
    format_critical_alert,
)


def test_no_tests_returns_no_data():
    report = compute_load_risk("p1", "Test Oyuncu", [])
    assert report.risk_label == "Veri Yok"
    assert report.risk_score == 0.0


def test_good_values_low_risk():
    tests = [
        {"protocol": "sprint_10m", "value": 1.72, "unit": "sn", "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 40.0, "unit": "cm", "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 18.5, "unit": "seviye", "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p2", "İyi Oyuncu", tests)
    assert report.risk_label == "Düşük"
    assert report.risk_score < 0.20


def test_bad_values_high_risk():
    tests = [
        {"protocol": "sprint_10m", "value": 2.10, "unit": "sn", "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 24.0, "unit": "cm", "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 13.5, "unit": "seviye", "test_date": "2026-06-01"},
        {"protocol": "vo2max", "value": 44.0, "unit": "ml/kg/min", "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p3", "Yorgun Oyuncu", tests)
    assert report.risk_label in ("Yüksek", "Kritik")
    assert len(report.flags) >= 3


def test_flags_contain_protocol_name():
    tests = [{"protocol": "cmj", "value": 20.0, "unit": "cm", "test_date": "2026-06-01"}]
    report = compute_load_risk("p4", "Test", tests)
    assert any("cmj" in f["protocol"] for f in report.flags)


def test_trend_lower_is_better_improving():
    # sprint süresi düşüyor → iyileşme (lower_is_better)
    pts = [
        {"test_date": "2026-01-01", "value": 1.95},
        {"test_date": "2026-02-01", "value": 1.88},
        {"test_date": "2026-03-01", "value": 1.80},
    ]
    t = compute_protocol_trend("sprint_10m", pts)
    assert t.direction == "improving"
    assert t.lower_is_better is True
    assert len(t.points) == 3


def test_trend_higher_is_better_worsening():
    # YoYo seviyesi düşüyor → kötüleşme
    pts = [
        {"test_date": "2026-01-01", "value": 18.0},
        {"test_date": "2026-02-01", "value": 16.0},
        {"test_date": "2026-03-01", "value": 14.0},
    ]
    t = compute_protocol_trend("yoyo_irl1", pts)
    assert t.direction == "worsening"


def test_trend_insufficient_with_one_point():
    t = compute_protocol_trend("cmj", [{"test_date": "2026-01-01", "value": 30.0}])
    assert t.direction == "insufficient"
    assert t.slope == 0.0


def test_format_critical_alert_contains_player_and_flags():
    tests = [
        {"protocol": "sprint_10m", "value": 2.10, "test_date": "2026-06-01"},
        {"protocol": "cmj", "value": 24.0, "test_date": "2026-06-01"},
        {"protocol": "yoyo_irl1", "value": 13.5, "test_date": "2026-06-01"},
        {"protocol": "vo2max", "value": 44.0, "test_date": "2026-06-01"},
    ]
    report = compute_load_risk("p5", "Yorgun", tests)
    assert report.risk_label == "Kritik"
    msg = format_critical_alert(report)
    assert "Kritik" in msg
    assert "Yorgun" in msg
    assert "•" in msg
