"""Compliance engine — KVKK sınıflandırma + toplu erişim anomali tespiti."""
from __future__ import annotations

from app.engine.compliance import (
    AccessEvent,
    classify_sensitivity,
    detect_access_anomalies,
)


def test_classify_sensitivity_special_category() -> None:
    for cat in ("health", "injury", "performance_test", "wellness", "gps_load", "medical"):
        assert classify_sensitivity(cat) == "ozel_nitelikli"
    # büyük/küçük harf duyarsız
    assert classify_sensitivity("HEALTH") == "ozel_nitelikli"


def test_classify_sensitivity_personal_and_general() -> None:
    assert classify_sensitivity("contract") == "kisisel"
    assert classify_sensitivity("salary") == "kisisel"
    assert classify_sensitivity("team_form") == "genel"
    assert classify_sensitivity("") == "genel"


def test_no_anomaly_below_threshold() -> None:
    # 5 farklı oyuncu, eşik 20 → anomali yok
    events = [
        AccessEvent(user_id=1, subject_id=s, data_category="injury", minute=float(s))
        for s in range(5)
    ]
    report = detect_access_anomalies(events)
    assert report.total_events == 5
    assert report.special_category_events == 5
    assert report.distinct_users == 1
    assert report.anomalies == ()


def test_bulk_access_flagged() -> None:
    # tek kullanıcı 5 dk içinde 25 farklı oyuncunun sağlık verisine erişiyor
    events = [
        AccessEvent(user_id=7, subject_id=s, data_category="health", minute=float(s) * 0.1)
        for s in range(25)
    ]
    report = detect_access_anomalies(events, window_min=60.0, bulk_threshold=20)
    assert len(report.anomalies) == 1
    anomaly = report.anomalies[0]
    assert anomaly.user_id == 7
    assert anomaly.distinct_subjects == 25


def test_window_resets_distinct_count() -> None:
    # 25 erişim ama her biri pencereden uzak (200 dk arayla) → eşzamanlı toplu yok
    events = [
        AccessEvent(user_id=7, subject_id=s, data_category="health", minute=float(s) * 200.0)
        for s in range(25)
    ]
    report = detect_access_anomalies(events, window_min=60.0, bulk_threshold=20)
    assert report.anomalies == ()


def test_non_special_category_ignored() -> None:
    # 25 sözleşme erişimi (kisisel, özel-nitelikli değil) → anomali yok
    events = [
        AccessEvent(user_id=7, subject_id=s, data_category="contract", minute=float(s) * 0.1)
        for s in range(25)
    ]
    report = detect_access_anomalies(events, bulk_threshold=20)
    assert report.special_category_events == 0
    assert report.anomalies == ()


def test_bulk_access_string_user_id() -> None:
    """KVKK: user_id artık str (User.id UUID) — string anahtar anomalisi."""
    events = [
        AccessEvent(user_id="uuid-abc", subject_id=s, data_category="health",
                    minute=s * 0.1)
        for s in range(25)
    ]
    report = detect_access_anomalies(events)
    assert report.anomalies
    assert report.anomalies[0].user_id == "uuid-abc"


def test_bulk_access_none_user_id_does_not_crash() -> None:
    """Eski/atıfsız kayıtlar (user_id=None) gruplanır, çökmez."""
    events = [
        AccessEvent(user_id=None, subject_id=s, data_category="health",
                    minute=s * 0.1)
        for s in range(25)
    ]
    report = detect_access_anomalies(events)
    assert report.anomalies
    assert report.anomalies[0].user_id is None
