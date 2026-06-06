"""Fiziksel test modülü unit testleri — saf engine (DB/API gerekmez)."""

from app.engine.physical.load_risk import compute_load_risk


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
