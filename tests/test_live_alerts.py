"""live_alerts — maç-içi proaktif uyarı motoru (J, saf)."""
from __future__ import annotations

from app.engine.live_alerts import compute_live_alerts


def test_momentum_break_critical_when_sustained():
    trend = {"momentum": {"direction": "rakibe doğru", "sustained_snapshots": 3}}
    r = compute_live_alerts(current_minute=70.0, momentum_trend=trend)
    assert r.critical == 1
    assert r.alerts[0].alert_type == "momentum_break"


def test_momentum_break_warning_when_short():
    trend = {"momentum": {"direction": "rakibe doğru", "sustained_snapshots": 2}}
    r = compute_live_alerts(current_minute=70.0, momentum_trend=trend)
    assert r.warning == 1
    assert r.critical == 0


def test_momentum_toward_us_no_alert():
    trend = {"momentum": {"direction": "bize doğru", "sustained_snapshots": 4}}
    r = compute_live_alerts(current_minute=70.0, momentum_trend=trend)
    assert r.total == 0


def test_fatigue_critical_and_warning():
    states = [{"player_id": 10, "fatigue": 0.95}, {"player_id": 8, "fatigue": 0.82}]
    r = compute_live_alerts(current_minute=70.0, player_states=states)
    assert r.critical == 1
    assert r.warning == 1
    # critical önce sıralanır
    assert r.alerts[0].severity == "critical"
    assert r.alerts[0].player_external_id == 10


def test_card_risk_critical():
    states = [{"player_id": 5, "yellow_card": True, "duel_loss_rate": 0.7}]
    r = compute_live_alerts(current_minute=70.0, player_states=states)
    assert any(a.alert_type == "card_risk" and a.severity == "critical"
               for a in r.alerts)


def test_yellow_without_duel_loss_no_card_alert():
    states = [{"player_id": 5, "yellow_card": True, "duel_loss_rate": 0.2}]
    r = compute_live_alerts(current_minute=70.0, player_states=states)
    assert not any(a.alert_type == "card_risk" for a in r.alerts)


def test_poor_data_quality_adds_info():
    r = compute_live_alerts(current_minute=70.0, data_quality_status="poor")
    assert r.info == 1
    assert r.alerts[0].alert_type == "data_quality"


def test_dedup_keys_stable():
    states = [{"player_id": 10, "fatigue": 0.95}]
    r = compute_live_alerts(current_minute=70.0, player_states=states)
    assert r.alerts[0].dedup_key == "fatigue:10"


def test_empty_inputs_no_alerts():
    r = compute_live_alerts(current_minute=70.0)
    assert r.total == 0
    assert r.alerts == ()
