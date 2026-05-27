"""OpenAPI metadata + tag organization tests (PR D2)."""

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


def test_openapi_has_app_description(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "Süper Lig" in spec["info"]["description"]
    assert spec["info"]["version"]


def test_openapi_has_tag_metadata(client):
    r = client.get("/openapi.json")
    spec = r.json()
    tag_names = {t["name"] for t in spec.get("tags", [])}
    assert {"ops", "catalog", "team-analysis", "match-analysis", "admin"} <= tag_names


def test_openapi_endpoints_have_summaries(client):
    """Major endpoint'ler summary'siz kalmasın (Swagger UI okunabilir olsun)."""
    r = client.get("/openapi.json")
    spec = r.json()
    paths = spec["paths"]
    # Beklediğimiz endpoint'ler:
    checked = [
        ("/health", "get"),
        ("/leagues", "get"),
        ("/teams/{team_id}/form", "get"),
        ("/teams/{team_id}/rating", "get"),
        ("/matches/{match_id}/predict", "get"),
    ]
    for path, method in checked:
        op = paths.get(path, {}).get(method, {})
        assert op, f"endpoint yok: {method.upper()} {path}"
        assert op.get("summary"), f"{method.upper()} {path} summary'siz"


def test_openapi_endpoints_have_tags(client):
    r = client.get("/openapi.json")
    spec = r.json()
    paths = spec["paths"]
    # Tag'siz kalmamış olmalı
    untagged = []
    for path, methods in paths.items():
        for method, op in methods.items():
            if method in ("get", "post", "put", "delete", "patch") and not op.get("tags"):
                untagged.append(f"{method.upper()} {path}")
    assert not untagged, f"Tag'siz endpoint'ler: {untagged}"
