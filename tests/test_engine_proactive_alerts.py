"""engine.proactive_alerts + available_squad tests."""
from __future__ import annotations

from app.engine.available_squad import compute_available_squad
from app.engine.proactive_alerts import compute_proactive_alerts

# --------------------------------------------------------------------------- #
# proactive_alerts
# --------------------------------------------------------------------------- #


def test_extreme_load_critical_alert():
    loads = [{"player_external_id": 100, "risk_level": "extreme",
              "minutes_per_week": 400.0, "back_to_back_count": 1}]
    r = compute_proactive_alerts(11, player_loads=loads).value
    assert r.critical_count >= 1
    assert any(a.alert_type == "high_load" and a.severity == "critical"
               for a in r.alerts)


def test_back_to_back_warning():
    loads = [{"player_external_id": 100, "risk_level": "medium",
              "minutes_per_week": 200.0, "back_to_back_count": 3}]
    r = compute_proactive_alerts(11, player_loads=loads).value
    assert any(a.alert_type == "back_to_back" for a in r.alerts)


def test_fixture_congestion_alert():
    r = compute_proactive_alerts(
        11, upcoming_count=4, dense_schedule=True, horizon_days=14,
    ).value
    assert any(a.alert_type == "fixture_congestion" for a in r.alerts)


def test_contract_expiry_critical():
    r = compute_proactive_alerts(
        11, contract_warnings=[{"player_id": 100, "months_left": 2}],
    ).value
    assert any(a.alert_type == "contract_expiry" and a.severity == "critical"
               for a in r.alerts)


def test_aging_core_info():
    r = compute_proactive_alerts(
        11, contract_warnings=[{"player_id": 100, "age": 34}],
    ).value
    assert any(a.alert_type == "aging_core" for a in r.alerts)


def test_severity_sorted():
    """Critical önce, info sonra."""
    loads = [{"player_external_id": 100, "risk_level": "extreme",
              "minutes_per_week": 400.0, "back_to_back_count": 1}]
    r = compute_proactive_alerts(
        11, player_loads=loads,
        contract_warnings=[{"player_id": 200, "age": 35}],
    ).value
    severities = [a.severity for a in r.alerts]
    # İlk eleman critical olmalı
    assert severities[0] == "critical"


def test_no_alerts_empty():
    r = compute_proactive_alerts(11).value
    assert r.total_alerts == 0


# --------------------------------------------------------------------------- #
# available_squad
# --------------------------------------------------------------------------- #


def test_injured_unavailable():
    squad = [{"player_id": 100, "injured": True}]
    r = compute_available_squad(11, squad).value
    assert r.unavailable_count == 1
    assert r.players[0].reason == "sakat"


def test_suspended_unavailable():
    squad = [{"player_id": 100, "suspended": True}]
    r = compute_available_squad(11, squad).value
    assert r.players[0].status == "unavailable"
    assert r.players[0].reason == "kart cezası"


def test_high_load_doubtful():
    squad = [{"player_id": 100, "risk_level": "high"}]
    r = compute_available_squad(11, squad).value
    assert r.doubtful_count == 1
    assert r.players[0].status == "doubtful"


def test_available_normal():
    squad = [{"player_id": 100, "risk_level": "low"}]
    r = compute_available_squad(11, squad).value
    assert r.available_count == 1


def test_mixed_squad_sorted():
    squad = [
        {"player_id": 1, "injured": True},
        {"player_id": 2, "risk_level": "low"},
        {"player_id": 3, "risk_level": "extreme"},
    ]
    r = compute_available_squad(11, squad).value
    assert r.available_count == 1
    assert r.doubtful_count == 1
    assert r.unavailable_count == 1
    # available önce
    assert r.players[0].status == "available"
