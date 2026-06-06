"""Performans testi (sports science) endpoint'leri."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.session import get_session


@pytest.fixture()
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_protocol_library_lists_tests(client):
    r = client.get("/admin/performance/protocols")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()["protocols"]}
    assert {"cmj", "sprint_30m", "yoyo_ir1"} <= keys


def test_score_endpoint_rates_and_percentile(client):
    r = client.post("/admin/performance/score", json={
        "protocol_key": "cmj", "raw_value": 42.0,
        "reference_values": [30, 32, 35, 38],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["rating"] == "elit"
    assert body["squad_percentile"] == 100.0


def test_battery_endpoint_profiles_player(client):
    r = client.post("/admin/performance/battery", json={
        "player_id": 217,
        "results": [["cmj", 42.0], ["sprint_30m", 4.6]],
    })
    assert r.status_code == 200
    body = r.json()
    assert any("Jump" in s for s in body["strong_areas"])
    assert any("Sprint" in s for s in body["weak_areas"])


def test_progression_endpoint_detects_regression(client):
    r = client.post("/admin/performance/progression", json={
        "protocol_key": "cmj",
        "values": [40, 41, 40, 33, 32, 31],
    })
    assert r.status_code == 200
    assert r.json()["regression_alert"] is True


def test_score_unknown_protocol_400_or_500(client):
    # bilinmeyen protokol → engine ValueError (FastAPI 500); en azından 200 değil
    r = client.post("/admin/performance/score", json={
        "protocol_key": "yok", "raw_value": 1.0,
    })
    assert r.status_code != 200
