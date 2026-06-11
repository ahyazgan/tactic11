"""Dashboard endpoint — HTML serving."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.session import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_dashboard_returns_html(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "tactic11" in body
    assert "X-API-Key" in body
    # Sürdürülen endpoint'ler dashboard.js içinde referans alınmalı
    assert "/admin/db-stats" in body
    assert "/admin/ml-model-status" in body
    assert "/admin/predict-accuracy" in body


def test_dashboard_is_public_no_auth_required(client):
    """Dashboard kendisi public; auth çağrıları JS'den gelir."""
    # Authsuz çağrı 200 dönmeli — header gönderme
    r = client.get("/dashboard")
    assert r.status_code == 200


def test_dashboard_not_in_openapi_schema(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    # include_in_schema=False ile gizli
    assert "/dashboard" not in paths
