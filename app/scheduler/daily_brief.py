"""Daily decision brief — günde bir kere, tüm aktif tenant'lar için.

Akış (tenant başına):
1. Bu haftaki maçları bul (kickoff between now and now+horizon_days, status NS)
2. Her maç için sırayla:
   - LineupRecommendationAgent (her takım için)
   - InjuryLoadAgent (her takım için)
   - PreMatchReportAgent (maç için)
3. Partial-success: bir agent fail olursa diğerleri devam eder
4. Webhook varsa tenant.settings_json'dan oku, HMAC-SHA256 ile imzala, POST et

Idempotency: agent_outputs tablosunda zaten bugün için kayıt varsa skip.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    InjuryLoadAgent,
    LineupRecommendationAgent,
    PreMatchReportAgent,
    save_agent_output,
)
from app.core.logging import get_logger
from app.db import models
from app.sports import football

log = get_logger(__name__)

AGENT_TIMEOUT_SECONDS = 300  # 5 dakika per agent (LLM yavaş olabilir)
WEBHOOK_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class TenantBriefResult:
    tenant_id: str
    tenant_slug: str
    matches_processed: int
    agents_succeeded: int
    agents_failed: int
    errors: list[str]


@dataclass(frozen=True)
class DailyBriefRunResult:
    run_at: datetime
    tenants_processed: int
    tenants_skipped: int
    per_tenant: list[TenantBriefResult]
    total_succeeded: int
    total_failed: int


def _tenant_settings(tenant: models.Tenant) -> dict[str, Any]:
    try:
        return json.loads(tenant.settings_json) if tenant.settings_json else {}
    except (json.JSONDecodeError, AttributeError):
        return {}


def _already_processed_today(
    session: Session, *, tenant_id: str, agent_name: str,
    subject_type: str, subject_id: int, now: datetime,
) -> bool:
    """Bu tenant için bu agent + subject bugün çalıştı mı."""
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    row = session.execute(
        select(models.AgentOutput).where(
            models.AgentOutput.tenant_id == tenant_id,
            models.AgentOutput.agent_name == agent_name,
            models.AgentOutput.subject_type == subject_type,
            models.AgentOutput.subject_id == subject_id,
            models.AgentOutput.updated_at >= today_start,
        )
    ).scalar_one_or_none()
    return row is not None


def run_brief_for_tenant(
    session: Session, *,
    tenant: models.Tenant,
    horizon_days: int = 7,
    force: bool = False,
    now: datetime | None = None,
) -> TenantBriefResult:
    """Tek tenant için brief — agent'ları çalıştır + idempotency."""
    now = now or datetime.now(UTC)
    horizon = now + timedelta(days=horizon_days)

    # Bu tenant'ın bu haftaki maçları
    # NOT: tenant_filter listener session.info'dan okur; biz session.info'a
    # tenant_id'yi koymuyoruz burada — bu fonksiyon "internal" çağrı ve
    # caller `tenant_bypass()` veya explicit tenant_id filter ile gelir.
    # Buraya gelirken tenant zaten parametrede; query'de tenant_id explicit:
    upcoming = list(
        session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.tenant_id == tenant.id,
                models.Match.kickoff > now,
                models.Match.kickoff <= horizon,
                ~models.Match.status.in_(football.FINISHED_STATUSES),
            ).order_by(models.Match.kickoff)
        ).scalars()
    )

    lineup_agent = LineupRecommendationAgent()
    pre_match_agent = PreMatchReportAgent()
    # InjuryLoadAgent player_external_ids context'i gerektirir; roster lookup
    # ayrı bir job'da yapılacak (Prompt 4 sonrası).
    _ = InjuryLoadAgent  # import keep for future use

    succeeded = failed = 0
    errors: list[str] = []

    def _run_and_save(
        agent_instance, *, context: dict[str, Any],
        agent_name: str, agent_version: str,
        subject_type: str, subject_id: int,
    ) -> bool:
        # Idempotency check
        if not force and _already_processed_today(
            session, tenant_id=tenant.id,
            agent_name=agent_name, subject_type=subject_type,
            subject_id=subject_id, now=now,
        ):
            return False  # skipped
        try:
            result = agent_instance.run(session, context=context)
            saved = save_agent_output(
                session, result=result,
                agent_name=agent_name, agent_version=agent_version,
            )
            # tenant_id'yi store sonrası set et (agent_outputs.tenant_id nullable)
            saved.tenant_id = tenant.id
            session.flush()
            return True
        except Exception as e:  # noqa: BLE001
            errors.append(
                f"{agent_name}:{subject_type}:{subject_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False

    for match in upcoming:
        # Lineup — her iki takım için
        for team_id in (match.home_team_external_id, match.away_team_external_id):
            ok = _run_and_save(
                lineup_agent,
                context={
                    "match_external_id": match.external_id,
                    "team_external_id": team_id,
                },
                agent_name=lineup_agent.name, agent_version=lineup_agent.version,
                subject_type="match", subject_id=match.external_id,
            )
            if ok is True:
                succeeded += 1
            elif errors and errors[-1].startswith(f"{lineup_agent.name}:"):
                failed += 1
            # else: idempotent skip — sayma

        # Injury — takım roster proxy gerektirir; placeholder atla
        # (gerçek injury_load player_external_ids gerektirir; bu daily job'da
        # roster lookup ekstra iş — şimdilik lineup ile elde edilen player ID'lerini
        # kullanmıyoruz. TODO: future)

        # Pre-match — maç bazlı
        ok = _run_and_save(
            pre_match_agent,
            context={"match_external_id": match.external_id},
            agent_name=pre_match_agent.name, agent_version=pre_match_agent.version,
            subject_type="match", subject_id=match.external_id,
        )
        if ok is True:
            succeeded += 1
        elif errors and errors[-1].startswith(f"{pre_match_agent.name}:"):
            failed += 1

    session.commit()
    return TenantBriefResult(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        matches_processed=len(upcoming),
        agents_succeeded=succeeded,
        agents_failed=failed,
        errors=errors,
    )


def run_daily_brief(
    session: Session, *,
    horizon_days: int = 7,
    force: bool = False,
    now: datetime | None = None,
) -> DailyBriefRunResult:
    """Tüm aktif tenant'lar için brief — tenant başına paralel değil, sırayla."""
    now = now or datetime.now(UTC)
    # Bypass'lı sorgu — tüm tenant'lara erişebilmek için
    from app.db.tenant_context import tenant_bypass
    with tenant_bypass():
        tenants = list(
            session.execute(
                select(models.Tenant).where(models.Tenant.active.is_(True))
            ).scalars()
        )

    per_tenant: list[TenantBriefResult] = []
    succeeded = failed = 0
    processed = skipped = 0
    for tenant in tenants:
        try:
            r = run_brief_for_tenant(
                session, tenant=tenant,
                horizon_days=horizon_days, force=force, now=now,
            )
            per_tenant.append(r)
            succeeded += r.agents_succeeded
            failed += r.agents_failed
            processed += 1

            # Webhook (opsiyonel)
            settings = _tenant_settings(tenant)
            webhook_url = settings.get("webhook_url")
            if webhook_url and r.agents_succeeded > 0:
                _deliver_webhook(
                    url=webhook_url,
                    secret=settings.get("webhook_secret", ""),
                    payload={
                        "tenant_id": tenant.id,
                        "tenant_slug": tenant.slug,
                        "matches_processed": r.matches_processed,
                        "agents_succeeded": r.agents_succeeded,
                        "agents_failed": r.agents_failed,
                        "run_at": now.isoformat(),
                    },
                )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "tenant brief failed tenant=%s: %s", tenant.id, e,
            )
            skipped += 1

    result = DailyBriefRunResult(
        run_at=now,
        tenants_processed=processed,
        tenants_skipped=skipped,
        per_tenant=per_tenant,
        total_succeeded=succeeded,
        total_failed=failed,
    )
    # Yapılandırılmış kanal varsa brief özetini telefona gönder (best-effort).
    _maybe_notify_brief(result)
    return result


def format_daily_brief_digest(result: DailyBriefRunResult) -> str:
    """Günlük brief sonucunu kısa, telefona uygun bir mesaja çevir (saf)."""
    when = result.run_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📋 Günlük brief — {when}",
        f"{result.tenants_processed} kulüp işlendi · "
        f"{result.total_succeeded} rapor üretildi"
        + (f" · {result.total_failed} hata" if result.total_failed else ""),
    ]
    for t in result.per_tenant:
        if t.agents_succeeded:
            lines.append(
                f"• {t.tenant_slug}: {t.matches_processed} maç, "
                f"{t.agents_succeeded} rapor"
            )
    return "\n".join(lines)


def _maybe_notify_brief(result: DailyBriefRunResult) -> None:
    """Yapılandırılmış bildirim kanalı varsa brief özetini gönder (best-effort).

    Hiç rapor üretilmediyse ya da kanal yoksa no-op. Gönderim hatası brief
    sonucunu etkilemez (scheduler job zaten tamamlandı)."""
    if result.total_succeeded <= 0:
        return
    try:
        from app.notifications import build_default_notifier
        notifier = build_default_notifier()
        if not notifier.active_channel_names():
            return
        notifier.send_all(format_daily_brief_digest(result))
    except Exception as e:  # noqa: BLE001 — bildirim brief'i bozmamalı
        log.warning("brief bildirimi gönderilemedi: %s", e)


def _deliver_webhook(
    *, url: str, secret: str, payload: dict[str, Any],
) -> bool:
    """HMAC-SHA256 imzalı POST. 3 retry exponential backoff (2s, 4s).

    4xx response → retry yok (config hatası). 5xx + network error → retry.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = ""
    if secret:
        signature = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Manager2-Signature"] = signature

    import time as _t
    last_status = 0
    for attempt in range(3):
        try:
            with httpx.Client(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                r = client.post(url, content=body, headers=headers)
                last_status = r.status_code
                if 200 <= r.status_code < 300:
                    return True
                if 400 <= r.status_code < 500:
                    log.warning(
                        "webhook %s 4xx %d (no retry): %s",
                        url, r.status_code, r.text[:200],
                    )
                    return False
                log.warning(
                    "webhook %s 5xx %d (attempt %d)",
                    url, r.status_code, attempt + 1,
                )
        except (httpx.HTTPError, OSError) as e:
            log.warning("webhook %s network error (attempt %d): %s", url, attempt + 1, e)
        _t.sleep(2 ** (attempt + 1))
    log.error("webhook %s failed after 3 retries (last_status=%d)", url, last_status)
    return False
