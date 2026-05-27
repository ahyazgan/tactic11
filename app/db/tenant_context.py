"""Tenant ContextVar — request-scoped current tenant.

FastAPI middleware request başında set eder; tenant_filter event listener
SQLAlchemy query'lerine `WHERE tenant_id = current` ekler.

Bypass: `with tenant_bypass(): ...` — sadece super-admin cross-tenant
endpoint'lerinde (örn. /admin/db-stats global sayım) explicit kullanılır.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# Migration 0011'deki sabit. App code'da DEFAULT_TENANT_ID kullanılabilir.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Hangi tenant'ın query'lerini filtreleyeceğimizi tutar.
# None → filtre uygulanmaz (testler + admin bypass için).
_current_tenant_id: ContextVar[str | None] = ContextVar(
    "current_tenant_id", default=None,
)

# Bypass flag — bilinçli olarak tüm tenant'ları sorgulamak isteyen
# super-admin endpoint'leri için.
_bypass: ContextVar[bool] = ContextVar("tenant_filter_bypass", default=False)


def current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: str | None) -> None:
    _current_tenant_id.set(tenant_id)


def is_bypassed() -> bool:
    return _bypass.get()


@contextmanager
def tenant_bypass() -> Iterator[None]:
    """Cross-tenant query yapmak isteyen super-admin için context manager.

    with tenant_bypass():
        all_teams = session.execute(select(Team)).all()  # tenant_id filtresiz
    """
    tok = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(tok)
