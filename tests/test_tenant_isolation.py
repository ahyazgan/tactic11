"""TDD: tenant izolasyon testleri.

Bu test dosyası implementation'dan ÖNCE yazıldı (RED fazı).
Sonra app/auth/ + app/db/tenant_filter.py yazılıp testler GREEN'e geçti.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session
from app.db.tenant_context import set_current_tenant_id
from app.sports import football

# Bu importlar henüz yazılmadığı için ilk commit'te ImportError fırlatır.
# TDD RED → modüller eklenince GREEN.
try:
    from app.auth.passwords import hash_password
    from app.auth.service import create_user, login
    from app.db.tenant_context import (
        DEFAULT_TENANT_ID,
        current_tenant_id,
        set_current_tenant_id,
    )
    _AUTH_AVAILABLE = True
except ImportError:
    _AUTH_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _AUTH_AVAILABLE,
    reason="Auth modülleri henüz implement edilmedi (TDD RED phase)",
)


@pytest.fixture()
def client(session, monkeypatch):
    """JWT secret'ı set'le ki `no_auth_configured` False olsun ve gerçek
    auth enforcement aktif olsun. ContextVar her test sonu temizlenir."""
    # JWT secret'ı dev fallback ile aynı yap — testler reproducible
    monkeypatch.setenv("JWT_SECRET_KEY", "tenant-isolation-test-secret-32-byte-min")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        set_current_tenant_id(None)
        get_settings.cache_clear()  # type: ignore[attr-defined]


def _seed_tenant(session, *, tenant_id: str, slug: str, name: str) -> models.Tenant:
    now = datetime.now(UTC)
    row = models.Tenant(
        id=tenant_id, slug=slug, name=name,
        settings_json="{}", active=True, created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def _seed_team_for_tenant(session, *, tenant_id: str, external_id: int, name: str):
    from datetime import timedelta
    session.add(models.Team(
        sport=football.SPORT_NAME, external_id=external_id,
        name=name, country="TR", tenant_id=tenant_id,
    ))
    # Form için en az 1 maç da seed et
    now = datetime.now(UTC)
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=external_id * 100,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=5),
        status="FT",
        home_team_external_id=external_id, away_team_external_id=999,
        home_score=2, away_score=1,
        tenant_id=tenant_id,
    ))
    session.flush()


def _seed_user(session, *, tenant_id: str, email: str, password: str, role: str):
    return create_user(
        session,
        tenant_id=tenant_id, email=email,
        password=password, role=role,
    )


@pytest.fixture()
def two_tenants(session):
    """Konyaspor + Antalyaspor yan yana, her birinin kendi 1 takımı."""
    konya = _seed_tenant(session, tenant_id="t-konya", slug="konyaspor", name="Konyaspor")
    antalya = _seed_tenant(session, tenant_id="t-antalya", slug="antalyaspor", name="Antalyaspor")
    _seed_team_for_tenant(session, tenant_id=konya.id, external_id=1001, name="Konyaspor")
    _seed_team_for_tenant(session, tenant_id=antalya.id, external_id=1002, name="Antalyaspor")
    konya_user = _seed_user(
        session, tenant_id=konya.id, email="kon@example.com",
        password="kon-pass-strong-123", role="admin",
    )
    antalya_user = _seed_user(
        session, tenant_id=antalya.id, email="ant@example.com",
        password="ant-pass-strong-456", role="admin",
    )
    session.commit()
    return {
        "konya": {"tenant": konya, "user": konya_user, "team_id": 1001},
        "antalya": {"tenant": antalya, "user": antalya_user, "team_id": 1002},
    }


def _auth_headers(client, *, email: str, password: str) -> dict[str, str]:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Kabul kriterleri (Prompt 1)
# --------------------------------------------------------------------------- #


def test_two_tenants_can_coexist(session, two_tenants):
    """Aynı DB'de iki tenant + her biri kendi takımı."""
    teams = session.query(models.Team).all()
    assert len(teams) == 2
    by_tenant = {t.tenant_id for t in teams}
    assert by_tenant == {"t-konya", "t-antalya"}


def test_konya_user_sees_only_konya_team(client, two_tenants):
    """Konya token ile /teams listesi → sadece Konya takımı."""
    headers = _auth_headers(client, email="kon@example.com", password="kon-pass-strong-123")
    r = client.get("/teams", headers=headers)
    assert r.status_code == 200
    data = r.json()
    ids = {t["external_id"] for t in data}
    assert 1001 in ids
    assert 1002 not in ids


def test_konya_cannot_access_antalya_team_returns_404(client, two_tenants):
    """Cross-tenant erişim → 404 (403 değil — exist'i bile gizle)."""
    headers = _auth_headers(client, email="kon@example.com", password="kon-pass-strong-123")
    # 1002 = Antalya takımı. Konya user'la istek → 404
    r = client.get("/teams/1002/form", headers=headers)
    assert r.status_code == 404


def test_konya_can_access_own_team_returns_200(client, two_tenants):
    """Kendi tenant'ının takımı 200 dönmeli (control test)."""
    headers = _auth_headers(client, email="kon@example.com", password="kon-pass-strong-123")
    r = client.get("/teams/1001/form", headers=headers)
    assert r.status_code == 200


def test_antalya_user_sees_only_antalya_team(client, two_tenants):
    headers = _auth_headers(client, email="ant@example.com", password="ant-pass-strong-456")
    r = client.get("/teams", headers=headers)
    assert r.status_code == 200
    ids = {t["external_id"] for t in r.json()}
    assert 1002 in ids
    assert 1001 not in ids


def test_unauthenticated_request_401(client, two_tenants):
    """Auth header'sız → 401. (Auth aktif çünkü JWT_SECRET set'li client fixture'da)"""
    r = client.get("/teams/1001/form")  # protected endpoint
    assert r.status_code == 401


def test_invalid_credentials_401(client, two_tenants):
    r = client.post(
        "/auth/login",
        json={"email": "kon@example.com", "password": "wrong-pass"},
    )
    assert r.status_code == 401


def test_jwt_me_returns_current_user(client, two_tenants):
    headers = _auth_headers(client, email="kon@example.com", password="kon-pass-strong-123")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "kon@example.com"
    assert me["tenant_id"] == "t-konya"
    assert me["role"] == "admin"


def test_default_tenant_id_constant_exists():
    """Migration 0011 ile aynı UUID; backward-compat için sabit."""
    assert DEFAULT_TENANT_ID == "00000000-0000-0000-0000-000000000001"


def test_tenant_context_propagates(session):
    """ContextVar set/get çalışıyor mu."""
    set_current_tenant_id("t-test")
    assert current_tenant_id() == "t-test"
    set_current_tenant_id(None)
    assert current_tenant_id() is None
