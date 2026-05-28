"""Test fikstürleri: izole, in-memory SQLite oturumu + multi-tenant fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  Base.metadata'yı doldurur
from app.db.base import Base
from app.db.tenant_context import DEFAULT_TENANT_ID, set_current_tenant_id


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Her test öncesinde rate limiter buckets'ı temizle.

    Module-level singleton (`app.api.main._rate_limiter`) testler arasında
    state taşır; 120 req/dk eşiğine ulaşınca sonraki test 429 alır.
    Bu fixture autouse=True ile her test öncesi reset eder.
    """
    try:
        from app.api.main import _rate_limiter
        with _rate_limiter._lock:
            _rate_limiter._window.clear()
    except (ImportError, AttributeError):
        pass
    yield


@pytest.fixture()
def session() -> Session:
    # StaticPool + check_same_thread=False: TestClient farklı thread'den de
    # aynı in-memory DB'ye ulaşsın.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False, future=True)
    s = SessionTest()
    # ContextVar temizliği — önceki test'ten kalan tenant_id sızmasın
    set_current_tenant_id(None)
    try:
        yield s
    finally:
        set_current_tenant_id(None)
        s.close()
        engine.dispose()


# --------------------------------------------------------------------------- #
# Multi-tenant test helpers (opt-in — mevcut testler değişmez)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def default_tenant(session) -> models.Tenant:
    """Migration 0011'in seed ettiği default tenant'ı in-memory test DB'sinde
    oluştur. (Test DB Base.metadata.create_all ile çıplak başlar; seed yok.)

    Bu fixture'ı kullanan testler tenant context'i set'liyse loader_criteria
    aktif olur — opt-in pattern.
    """
    now = datetime.now(UTC)
    tenant = models.Tenant(
        id=DEFAULT_TENANT_ID,
        slug="default",
        name="Default Tenant",
        settings_json="{}",
        active=True,
        created_at=now,
    )
    session.add(tenant)
    session.flush()
    return tenant


@pytest.fixture()
def test_user(session, default_tenant) -> models.User:
    """Default tenant'a admin rolünde bir test user."""
    from app.auth.service import create_user
    user = create_user(
        session,
        tenant_id=default_tenant.id,
        email="test@example.com",
        password="test-password-1234",
        role="admin",
    )
    session.flush()
    return user
