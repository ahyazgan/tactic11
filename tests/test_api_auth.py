"""API key auth davranışı.

Settings lru_cache'lendiği için modül-import edilen get_settings referansını
monkeypatch'liyoruz (gerçek env'i değiştirmiyoruz).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.api.main import app
from app.core.config import Settings
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


def _force_key(monkeypatch, key: str) -> None:
    fake = Settings(API_AUTH_KEY=key)
    monkeypatch.setattr(auth_module, "get_settings", lambda: fake)


def test_health_always_open(client, monkeypatch):
    _force_key(monkeypatch, "secret")
    r = client.get("/health")
    assert r.status_code == 200


def test_protected_endpoint_denies_without_key(client, monkeypatch):
    _force_key(monkeypatch, "secret")
    r = client.get("/leagues")
    assert r.status_code == 401


def test_protected_endpoint_accepts_correct_key(client, monkeypatch):
    _force_key(monkeypatch, "secret")
    r = client.get("/leagues", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


def test_protected_endpoint_rejects_wrong_key(client, monkeypatch):
    _force_key(monkeypatch, "secret")
    r = client.get("/leagues", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_empty_config_disables_auth(client, monkeypatch):
    _force_key(monkeypatch, "")
    r = client.get("/leagues")
    assert r.status_code == 200
