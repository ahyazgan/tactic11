"""Fiziksel test modülü testleri — saf engine + endpoint (in-memory SQLite)."""

import types

import pytest
from fastapi.testclient import TestClient

import app.db.physical_test  # noqa: F401 — PhysicalTest tablosunu metadata'ya kaydet
from app.api.auth import get_current_user
from app.api.main import app
from app.db.session import get_session
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


# --------------------------------------------------------------------------- #
# Endpoint testleri — JWT + tenant izolasyonu (sahte get_current_user override)
# --------------------------------------------------------------------------- #

_SPRINT_OK = {
    "player_id": "12345", "player_name": "Rafa Silva",
    "test_date": "2026-06-06", "protocol": "sprint_10m", "value": 1.78,
}


@pytest.fixture()
def client(session):
    """TestClient + override edilmiş DB session ve current_user.

    `state["tenant_id"]` değiştirilerek cross-tenant senaryosu kurulur."""
    state = {"tenant_id": "t1", "email": "coach@besiktas.com"}

    def _fake_user():
        return types.SimpleNamespace(
            id="u1", tenant_id=state["tenant_id"], email=state["email"],
        )

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        yield TestClient(app), state
    finally:
        app.dependency_overrides.clear()


def test_post_returns_201_autofills_unit_and_recorded_by(client):
    c, _ = client
    r = c.post("/physical-tests/", json=_SPRINT_OK)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["protocol"] == "sprint_10m"
    assert body["unit"] == "sn"                       # protokolden otomatik
    assert body["recorded_by"] == "coach@besiktas.com"  # current_user.email
    assert body["player_id"] == "12345"


def test_post_ignores_tenant_from_body(client):
    """tenant_id gövdeden gelse bile current_user'dan alınır (sızıntı yok)."""
    c, state = client
    payload = {**_SPRINT_OK, "tenant_id": "baska-kulup"}
    r = c.post("/physical-tests/", json=payload)
    assert r.status_code == 201
    # t2 olarak bakınca görünmemeli → tenant t1'e yazılmış demektir
    state["tenant_id"] = "t2"
    assert c.get("/physical-tests/12345").json() == []


def test_get_risk_schema(client):
    c, _ = client
    c.post("/physical-tests/", json=_SPRINT_OK)
    r = c.get("/physical-tests/12345/risk")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "player_id", "player_name", "risk_score",
        "risk_label", "flags", "summary", "recommendations",
    ):
        assert key in body


def test_get_risk_404_when_no_data(client):
    c, _ = client
    assert c.get("/physical-tests/99999/risk").status_code == 404


def test_cross_tenant_isolation(client):
    c, state = client
    r = c.post("/physical-tests/", json=_SPRINT_OK)
    assert r.status_code == 201
    test_id = r.json()["id"]

    # Başka kulüp (t2) ne listeyi, ne riski, ne silmeyi yapabilmeli.
    state["tenant_id"] = "t2"
    assert c.get("/physical-tests/12345").json() == []
    assert c.get("/physical-tests/12345/risk").status_code == 404
    assert c.delete(f"/physical-tests/{test_id}").status_code == 404

    # Sahibi (t1) silebilmeli.
    state["tenant_id"] = "t1"
    assert c.delete(f"/physical-tests/{test_id}").status_code == 204
    assert c.get("/physical-tests/12345").json() == []
