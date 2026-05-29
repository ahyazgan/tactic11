"""Faz 10 analiz endpoint'leri — what-if / backtest / anomaly / development-curve."""
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


def test_what_if_single_removal(client):
    r = client.post("/admin/analysis/what-if", json={
        "baseline_team_metric": 1.0,
        "contributions": [
            {"player_id": 10, "contribution": 0.5},
            {"player_id": 8, "contribution": 0.3},
            {"player_id": 4, "contribution": 0.2},
        ],
        "remove_player_id": 10,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["removed_player_id"] == 10
    assert body["delta"] < 0


def test_what_if_ranking_when_no_remove_id(client):
    r = client.post("/admin/analysis/what-if", json={
        "baseline_team_metric": 1.0,
        "contributions": [
            {"player_id": 10, "contribution": 0.5},
            {"player_id": 4, "contribution": 0.2},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["safest_to_remove"] == 4
    assert body["most_costly_to_remove"] == 10


def test_backtest_endpoint(client):
    r = client.post("/admin/analysis/backtest", json={
        "samples": [[0.9, True], [0.8, True], [0.1, False], [0.2, False]],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["hit_rate"] == 1.0
    assert body["brier_score"] < 0.1


def test_anomaly_endpoint_detects_spike(client):
    r = client.post("/admin/analysis/anomaly", json={
        "series": [1.0, 1.1, 0.9, 1.0, 5.0, 1.0, 0.95],
    })
    assert r.status_code == 200
    body = r.json()
    assert any(a["index"] == 4 for a in body["anomalies"])


def test_development_curve_endpoint_rising(client):
    r = client.post("/admin/analysis/development-curve", json={
        "values": [0.2, 0.4, 0.6, 0.8, 1.0],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["direction"] == "yükseliş"
    assert body["projection_next"] > 1.0


def test_analysis_empty_payload_safe(client):
    # Boş seri → patlamamalı (engine None/0 döner)
    r = client.post("/admin/analysis/anomaly", json={"series": []})
    assert r.status_code == 200
    assert r.json()["n"] == 0
