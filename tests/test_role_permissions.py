"""Role-based access kontrolü — require_role dependency factory."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import (
    get_current_user,
    require_role,
    router as auth_router,
)
from app.auth.service import create_user
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session


def _build_test_app() -> FastAPI:
    """Yalnız role guard'lı endpoint'leri test için minimal app."""
    app = FastAPI()
    app.include_router(auth_router)
    admin_only = APIRouter(prefix="/admin-test")

    @admin_only.get("/secret", dependencies=[Depends(require_role(["admin"]))])
    def admin_secret():
        return {"ok": True}

    @admin_only.get("/analyst-or-admin", dependencies=[Depends(require_role(["admin", "analyst"]))])
    def analyst_or_admin():
        return {"ok": True}

    @admin_only.get("/me")
    def whoami(user: models.User = Depends(get_current_user)):
        return {"role": user.role, "email": user.email}

    app.include_router(admin_only)
    return app


@pytest.fixture()
def client(session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-role-secret-32-byte-min-length")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    app = _build_test_app()

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture()
def four_users(session):
    """4 farklı rol, hepsi aynı tenant'ta."""
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-acme", slug="acme", name="Acme",
        settings_json="{}", active=True, created_at=now,
    ))
    users = {}
    for role in ("admin", "analyst", "coach", "viewer"):
        u = create_user(
            session, tenant_id="t-acme", email=f"{role}@x.com",
            password=f"{role}-pass-1234", role=role,
        )
        users[role] = u
    session.commit()
    return users


def _login(client, *, role: str) -> str:
    r = client.post("/auth/login", json={
        "email": f"{role}@x.com", "password": f"{role}-pass-1234",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_admin_can_access_admin_only(client, four_users):
    token = _login(client, role="admin")
    r = client.get("/admin-test/secret", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.parametrize("role", ["analyst", "coach", "viewer"])
def test_non_admin_403_on_admin_only(client, four_users, role):
    token = _login(client, role=role)
    r = client.get("/admin-test/secret", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "not allowed" in r.json()["detail"]


def test_analyst_or_admin_endpoint(client, four_users):
    # admin + analyst → 200
    for role in ("admin", "analyst"):
        token = _login(client, role=role)
        r = client.get(
            "/admin-test/analyst-or-admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"role={role}"
    # coach + viewer → 403
    for role in ("coach", "viewer"):
        token = _login(client, role=role)
        r = client.get(
            "/admin-test/analyst-or-admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


def test_me_endpoint_reflects_user_role(client, four_users):
    token = _login(client, role="coach")
    r = client.get("/admin-test/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["role"] == "coach"


def test_no_auth_header_401_on_role_endpoint(client, four_users):
    r = client.get("/admin-test/secret")
    assert r.status_code == 401
