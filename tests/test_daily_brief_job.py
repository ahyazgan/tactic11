"""Daily decision brief — multi-tenant scheduler job (Prompt 3)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db import models
from app.scheduler.daily_brief import (
    _deliver_webhook,
    run_brief_for_tenant,
    run_daily_brief,
)
from app.scheduler.registry import get
from app.sports import football


def _seed_tenant_with_match(
    session, *, tenant_id: str, slug: str, match_id: int, base: datetime,
) -> models.Tenant:
    tenant = models.Tenant(
        id=tenant_id, slug=slug, name=slug,
        settings_json="{}", active=True, created_at=base,
    )
    session.add(tenant)
    session.add_all([
        models.Team(sport=football.SPORT_NAME, external_id=611, name="Gala", tenant_id=tenant_id),
        models.Team(sport=football.SPORT_NAME, external_id=607, name="Fener", tenant_id=tenant_id),
        # Future match
        models.Match(
            sport=football.SPORT_NAME, external_id=match_id,
            league_external_id=203, season=2024,
            kickoff=base + timedelta(days=3), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
            tenant_id=tenant_id,
        ),
        # Past match for form
        models.Match(
            sport=football.SPORT_NAME, external_id=match_id + 1000,
            league_external_id=203, season=2024,
            kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=611, away_team_external_id=999,
            home_score=2, away_score=1,
            tenant_id=tenant_id,
        ),
    ])
    session.flush()
    return tenant


# --------------------------------------------------------------------------- #
# run_brief_for_tenant
# --------------------------------------------------------------------------- #


def test_brief_for_tenant_processes_upcoming_matches(session):
    base = datetime.now(UTC)
    tenant = _seed_tenant_with_match(
        session, tenant_id="t-a", slug="alpha", match_id=99, base=base,
    )
    r = run_brief_for_tenant(session, tenant=tenant, now=base)
    assert r.matches_processed == 1
    # 2 lineup (her takım için) + 1 pre_match = 3 success target
    assert r.agents_succeeded >= 1


def test_brief_idempotent_second_run_skips(session):
    base = datetime.now(UTC)
    tenant = _seed_tenant_with_match(
        session, tenant_id="t-a", slug="alpha", match_id=99, base=base,
    )
    r1 = run_brief_for_tenant(session, tenant=tenant, now=base)
    succeeded_first = r1.agents_succeeded
    assert succeeded_first >= 1
    # İkinci run — aynı gün
    r2 = run_brief_for_tenant(session, tenant=tenant, now=base)
    # İkinci kez 0 yeni success (hepsi skip)
    assert r2.agents_succeeded == 0


def test_brief_force_bypasses_idempotency(session):
    base = datetime.now(UTC)
    tenant = _seed_tenant_with_match(
        session, tenant_id="t-a", slug="alpha", match_id=99, base=base,
    )
    r1 = run_brief_for_tenant(session, tenant=tenant, now=base)
    r2 = run_brief_for_tenant(session, tenant=tenant, now=base, force=True)
    # Force ile yeniden çalışmalı → success > 0
    assert r2.agents_succeeded >= r1.agents_succeeded


# --------------------------------------------------------------------------- #
# run_daily_brief (multi-tenant)
# --------------------------------------------------------------------------- #


def test_daily_brief_iterates_all_active_tenants(session):
    base = datetime.now(UTC)
    _seed_tenant_with_match(session, tenant_id="t-a", slug="alpha", match_id=99, base=base)
    _seed_tenant_with_match(session, tenant_id="t-b", slug="beta", match_id=100, base=base)
    session.commit()
    result = run_daily_brief(session, now=base)
    assert result.tenants_processed == 2
    slugs = {r.tenant_slug for r in result.per_tenant}
    assert slugs == {"alpha", "beta"}


def test_daily_brief_skips_inactive_tenant(session):
    base = datetime.now(UTC)
    t = _seed_tenant_with_match(session, tenant_id="t-a", slug="alpha", match_id=99, base=base)
    t.active = False
    session.commit()
    result = run_daily_brief(session, now=base)
    assert result.tenants_processed == 0


# --------------------------------------------------------------------------- #
# Webhook delivery
# --------------------------------------------------------------------------- #


def test_webhook_signature_hmac_sha256(monkeypatch):
    """Webhook gönderildiğinde HMAC-SHA256 imzası doğru hesaplanmalı."""
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, *, content, headers):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers

            class _R:
                status_code = 200
                text = "ok"

            return _R()

    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    ok = _deliver_webhook(
        url="https://example.com/hook",
        secret="my-secret-32-byte",
        payload={"tenant_id": "t-a", "x": 1},
    )
    assert ok is True
    body = captured["content"]
    sig = captured["headers"]["X-Manager2-Signature"]
    # Manuel hesap
    expected = hmac.new(b"my-secret-32-byte", body, hashlib.sha256).hexdigest()
    assert sig == expected


def test_webhook_4xx_no_retry(monkeypatch):
    """4xx response → retry yok."""
    call_count = {"n": 0}

    class _Fake4xx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, *, content, headers):
            call_count["n"] += 1

            class _R:
                status_code = 400
                text = "bad request"

            return _R()

    import httpx
    monkeypatch.setattr(httpx, "Client", _Fake4xx)
    ok = _deliver_webhook(url="https://x.com", secret="", payload={"a": 1})
    assert ok is False
    assert call_count["n"] == 1  # tek deneme, retry yok


def test_webhook_skipped_if_no_url(session, monkeypatch):
    """tenant settings.webhook_url yoksa webhook gönderilmez (no error)."""
    base = datetime.now(UTC)
    tenant = _seed_tenant_with_match(
        session, tenant_id="t-a", slug="alpha", match_id=99, base=base,
    )
    # settings_json boş → webhook_url yok
    assert json.loads(tenant.settings_json) == {}
    session.commit()
    # Hiç çağrılmasın
    called = {"n": 0}
    from app.scheduler import daily_brief as db_mod

    def _spy(*a, **kw):
        called["n"] += 1
        return True

    monkeypatch.setattr(db_mod, "_deliver_webhook", _spy)
    run_daily_brief(session, now=base)
    assert called["n"] == 0


# --------------------------------------------------------------------------- #
# Job registration
# --------------------------------------------------------------------------- #


def test_daily_decision_brief_job_registered():
    spec = get("daily_decision_brief")
    assert spec.name == "daily_decision_brief"
    assert callable(spec.handler)
