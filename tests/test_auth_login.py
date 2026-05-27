"""Auth login + service.create_user testleri."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth.passwords import hash_password, verify_password
from app.auth.service import (
    InvalidCredentials,
    UserExists,
    create_user,
    login,
)
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session


@pytest.fixture()
def client(session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-login-32-byte-minimum")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _seed_tenant(session, *, slug="acme", tenant_id="t-acme") -> models.Tenant:
    now = datetime.now(UTC)
    t = models.Tenant(
        id=tenant_id, slug=slug, name=slug.title(),
        settings_json="{}", active=True, created_at=now,
    )
    session.add(t)
    session.flush()
    return t


# --------------------------------------------------------------------------- #
# passwords
# --------------------------------------------------------------------------- #


def test_hash_password_returns_string_and_verifies():
    h = hash_password("hello-world-1234")
    assert isinstance(h, str)
    assert len(h) >= 60  # bcrypt çıktı uzunluğu
    assert verify_password("hello-world-1234", h) is True
    assert verify_password("wrong", h) is False


def test_empty_password_raises():
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_handles_invalid_hash_gracefully():
    assert verify_password("any", "not-a-valid-hash") is False
    assert verify_password("any", "") is False


# --------------------------------------------------------------------------- #
# service.create_user
# --------------------------------------------------------------------------- #


def test_create_user_inserts(session):
    _seed_tenant(session)
    user = create_user(
        session, tenant_id="t-acme", email="u@x.com",
        password="strongpass-1234", role="admin",
    )
    assert user.id
    assert user.email == "u@x.com"
    assert user.tenant_id == "t-acme"
    assert user.role == "admin"
    assert user.password_hash != "strongpass-1234"  # hash, plaintext değil


def test_create_user_duplicate_raises(session):
    _seed_tenant(session)
    create_user(
        session, tenant_id="t-acme", email="u@x.com",
        password="pass-1234", role="admin",
    )
    with pytest.raises(UserExists):
        create_user(
            session, tenant_id="t-acme", email="u@x.com",
            password="other-pass", role="viewer",
        )


def test_create_user_same_email_different_tenant_ok(session):
    """Cross-tenant aynı email mümkün olmalı (unique scope tenant_id + email)."""
    _seed_tenant(session, slug="a", tenant_id="t-a")
    _seed_tenant(session, slug="b", tenant_id="t-b")
    create_user(session, tenant_id="t-a", email="dup@x.com", password="p" * 10, role="admin")
    # Bu fail etmemeli
    u = create_user(session, tenant_id="t-b", email="dup@x.com", password="p" * 10, role="admin")
    assert u.tenant_id == "t-b"


def test_create_user_invalid_role_raises(session):
    _seed_tenant(session)
    with pytest.raises(ValueError, match="role"):
        create_user(
            session, tenant_id="t-acme", email="u@x.com",
            password="p" * 10, role="ceo",  # geçersiz
        )


# --------------------------------------------------------------------------- #
# service.login
# --------------------------------------------------------------------------- #


def test_login_returns_token_pair(session):
    _seed_tenant(session)
    create_user(
        session, tenant_id="t-acme", email="u@x.com",
        password="strongpass-1234", role="admin",
    )
    pair = login(session, email="u@x.com", password="strongpass-1234")
    assert pair.access_token
    assert pair.refresh_token
    assert pair.access_token != pair.refresh_token


def test_login_wrong_password_raises(session):
    _seed_tenant(session)
    create_user(session, tenant_id="t-acme", email="u@x.com",
                password="p" * 10, role="admin")
    with pytest.raises(InvalidCredentials):
        login(session, email="u@x.com", password="wrong")


def test_login_inactive_user_raises(session):
    _seed_tenant(session)
    u = create_user(session, tenant_id="t-acme", email="u@x.com",
                    password="p" * 10, role="admin")
    u.active = False
    session.flush()
    with pytest.raises(InvalidCredentials):
        login(session, email="u@x.com", password="p" * 10)


def test_login_with_tenant_slug_filters(session):
    """Aynı email iki tenant'ta — slug ayrımı."""
    _seed_tenant(session, slug="a", tenant_id="t-a")
    _seed_tenant(session, slug="b", tenant_id="t-b")
    create_user(session, tenant_id="t-a", email="d@x.com", password="aaa" * 4, role="admin")
    create_user(session, tenant_id="t-b", email="d@x.com", password="bbb" * 4, role="admin")
    # Slug "a" + a şifresi → OK
    pair_a = login(session, email="d@x.com", password="aaa" * 4, tenant_slug="a")
    assert pair_a.access_token
    # Slug "a" + b şifresi → fail (tenant a'da o şifre yok)
    with pytest.raises(InvalidCredentials):
        login(session, email="d@x.com", password="bbb" * 4, tenant_slug="a")


def test_login_updates_last_login_at(session):
    _seed_tenant(session)
    u = create_user(session, tenant_id="t-acme", email="u@x.com",
                    password="p" * 10, role="admin")
    assert u.last_login_at is None
    login(session, email="u@x.com", password="p" * 10)
    assert u.last_login_at is not None


# --------------------------------------------------------------------------- #
# /auth/login endpoint
# --------------------------------------------------------------------------- #


def test_login_endpoint_200(client, session):
    _seed_tenant(session)
    create_user(session, tenant_id="t-acme", email="u@x.com",
                password="strongpass-1234", role="admin")
    session.commit()
    r = client.post("/auth/login", json={
        "email": "u@x.com", "password": "strongpass-1234",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_endpoint_401_on_wrong_password(client, session):
    _seed_tenant(session)
    create_user(session, tenant_id="t-acme", email="u@x.com",
                password="strongpass-1234", role="admin")
    session.commit()
    r = client.post("/auth/login", json={
        "email": "u@x.com", "password": "wrong",
    })
    assert r.status_code == 401


def test_me_endpoint_returns_current_user(client, session):
    _seed_tenant(session)
    create_user(session, tenant_id="t-acme", email="u@x.com",
                password="p" * 10, role="coach")
    session.commit()
    r = client.post("/auth/login", json={"email": "u@x.com", "password": "p" * 10})
    token = r.json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "u@x.com"
    assert me["role"] == "coach"
    assert me["tenant_id"] == "t-acme"
    assert me["tenant_slug"] == "acme"
