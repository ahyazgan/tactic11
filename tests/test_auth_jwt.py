"""JWT issue/decode + expiry + refresh rotation testleri."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as jwt_lib
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth.jwt_tokens import (
    create_access_token,
    create_refresh_token_value,
    decode_access_token,
)
from app.auth.service import (
    TokenExpired,
    create_user,
    login,
    logout,
    refresh_access,
)
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session


@pytest.fixture()
def client(session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-32-byte-minimum-len")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _seed(session, *, tenant_id="t-acme", slug="acme"):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id=tenant_id, slug=slug, name=slug.title(),
        settings_json="{}", active=True, created_at=now,
    ))
    user = create_user(
        session, tenant_id=tenant_id, email="u@x.com",
        password="strongpass-1234", role="admin",
    )
    session.flush()
    return user


# --------------------------------------------------------------------------- #
# JWT creation + decode
# --------------------------------------------------------------------------- #


def test_create_access_token_returns_jwt_string():
    tok = create_access_token(user_id="u1", tenant_id="t1", role="admin")
    parts = tok.split(".")
    assert len(parts) == 3  # JWT 3-part


def test_decode_returns_expected_claims():
    tok = create_access_token(user_id="u1", tenant_id="t1", role="admin")
    claims = decode_access_token(tok)
    assert claims.sub == "u1"
    assert claims.tenant_id == "t1"
    assert claims.role == "admin"
    assert claims.exp > claims.iat


def test_decode_invalid_token_raises():
    with pytest.raises(jwt_lib.PyJWTError):
        decode_access_token("not.a.valid.token")


def test_decode_expired_token_raises():
    """expires_minutes=-1 → token zaten süresi geçmiş üretilir."""
    tok = create_access_token(
        user_id="u", tenant_id="t", role="viewer", expires_minutes=-1,
    )
    with pytest.raises(jwt_lib.ExpiredSignatureError):
        decode_access_token(tok)


def test_create_refresh_token_is_random_64_hex():
    a = create_refresh_token_value()
    b = create_refresh_token_value()
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)
    assert a != b  # cryptographic random


# --------------------------------------------------------------------------- #
# Refresh rotation
# --------------------------------------------------------------------------- #


def test_refresh_returns_new_pair(session, client):
    _seed(session)
    session.commit()
    pair = login(session, email="u@x.com", password="strongpass-1234")
    session.commit()
    new_pair = refresh_access(session, refresh_token=pair.refresh_token)
    session.commit()
    assert new_pair.access_token != pair.access_token
    assert new_pair.refresh_token != pair.refresh_token


def test_refresh_old_token_revoked_after_rotation(session, client):
    """Token rotation güvenlik: eski refresh kullanılırsa fail (replay detection)."""
    _seed(session)
    session.commit()
    pair = login(session, email="u@x.com", password="strongpass-1234")
    session.commit()
    refresh_access(session, refresh_token=pair.refresh_token)
    session.commit()
    # Eski refresh tekrar kullanılırsa fail
    with pytest.raises(TokenExpired):
        refresh_access(session, refresh_token=pair.refresh_token)


def test_refresh_expired_token_raises(session, client):
    _seed(session)
    session.commit()
    pair = login(session, email="u@x.com", password="strongpass-1234")
    session.commit()
    # Refresh row'u manuel olarak süresi geçmiş yap
    import hashlib
    token_hash = hashlib.sha256(pair.refresh_token.encode()).hexdigest()
    row = session.query(models.RefreshToken).filter_by(token_hash=token_hash).one()
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    session.flush()
    with pytest.raises(TokenExpired):
        refresh_access(session, refresh_token=pair.refresh_token)


def test_logout_revokes_refresh(session, client):
    _seed(session)
    session.commit()
    pair = login(session, email="u@x.com", password="strongpass-1234")
    session.commit()
    assert logout(session, refresh_token=pair.refresh_token) is True
    session.commit()
    # İkinci logout → False (zaten revoked)
    assert logout(session, refresh_token=pair.refresh_token) is False
    # Revoke sonrası refresh fail
    with pytest.raises(TokenExpired):
        refresh_access(session, refresh_token=pair.refresh_token)


# --------------------------------------------------------------------------- #
# Endpoint flow
# --------------------------------------------------------------------------- #


def test_login_then_refresh_endpoint_flow(client, session):
    _seed(session)
    session.commit()
    # Login
    r = client.post("/auth/login", json={"email": "u@x.com", "password": "strongpass-1234"})
    assert r.status_code == 200
    rt1 = r.json()["refresh_token"]
    # Refresh
    r = client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r.status_code == 200
    rt2 = r.json()["refresh_token"]
    assert rt1 != rt2
    # Old refresh fail
    r = client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r.status_code == 401


def test_logout_endpoint_flow(client, session):
    _seed(session)
    session.commit()
    r = client.post("/auth/login", json={"email": "u@x.com", "password": "strongpass-1234"})
    rt = r.json()["refresh_token"]
    r = client.post("/auth/logout", json={"refresh_token": rt})
    assert r.status_code == 200
    assert r.json()["revoked"] is True
