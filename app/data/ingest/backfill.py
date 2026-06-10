"""Appearance backfill çekirdeği — FT maçlar için lineup + player-stats ingest.

`scripts/backfill_appearances.py` CLI'ı ve `appearance_backfill` scheduler
job'ı bu modülü çağırır; `scripts/sync_league.py --appearances N` ile sync
sonrası zincirlenir. Quota-aware (günlük limitin %80'inde durur) ve
idempotent (ingest edilmiş maçlar atlanır) — kurallar Prompt 4 ile aynı.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.ingest.player_appearance import ingest_appearances_for_match
from app.data.sources.api_football import APIFootball
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

log = get_logger(__name__)

# Default quota guard: günlük limit'in %80'ine ulaşınca dur (Prompt 4 kuralı)
DEFAULT_QUOTA_FRACTION_STOP = 0.80


def matches_to_backfill(
    session: Session, *,
    tenant_id: str | None,
    force: bool = False,
    limit: int | None = None,
) -> list[models.Match]:
    """Ingest edilecek maçları seç — FT statüsü + tenant filtresi.

    force=False iken player_appearances'ta satırı olan maçlar atlanır
    (idempotent + quota dostu). En yeni maçlar önce.
    """
    stmt = select(models.Match).where(
        models.Match.sport == football.SPORT_NAME,
        models.Match.status.in_(football.FINISHED_STATUSES),
    )
    if tenant_id:
        stmt = stmt.where(models.Match.tenant_id == tenant_id)
    stmt = stmt.order_by(models.Match.kickoff.desc())
    if limit:
        stmt = stmt.limit(limit * 3)  # skip dahil pad
    all_matches = list(session.execute(stmt).scalars())
    if force:
        return all_matches[: (limit or len(all_matches))]

    out: list[models.Match] = []
    for m in all_matches:
        existing = session.scalar(
            select(func.count()).select_from(models.PlayerAppearance).where(
                models.PlayerAppearance.match_external_id == m.external_id,
                models.PlayerAppearance.tenant_id == tenant_id,
            )
        )
        if not existing:
            out.append(m)
            if limit and len(out) >= limit:
                break
    return out


def current_quota_used(session: Session, *, today_only: bool = True) -> int:
    """Bugünkü API-Football çağrı sayısı (UsageEvent'ten)."""
    stmt = select(func.count()).select_from(models.UsageEvent).where(
        models.UsageEvent.source == "api_football",
    )
    if today_only:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = stmt.where(models.UsageEvent.created_at >= start)
    return int(session.scalar(stmt) or 0)


def backfill_appearances(
    *, tenant_id: str,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    quota_stop_fraction: float = DEFAULT_QUOTA_FRACTION_STOP,
    source: APIFootball | None = None,
) -> dict[str, float]:
    """FT maçlar için appearance backfill çalıştır + rapor döndür.

    source parametresi test enjeksiyonu içindir; verilmezse APIFootball().
    """
    from app.core.config import get_settings
    settings = get_settings()
    quota_limit = settings.api_football_daily_limit
    quota_stop = int(quota_limit * quota_stop_fraction)

    src = source or APIFootball()
    started = time.time()
    processed = skipped = failed = 0

    with SessionLocal() as session:
        # Tenant context — yeni satırlar bu tenant'a yazılsın
        session.info["tenant_id"] = tenant_id

        candidates = matches_to_backfill(
            session, tenant_id=tenant_id, force=force, limit=limit,
        )
        total_target = len(candidates)
        log.info(
            "backfill başlıyor: tenant=%s candidates=%d limit=%s force=%s dry_run=%s",
            tenant_id, total_target, limit, force, dry_run,
        )
        if dry_run:
            return {
                "candidates": total_target,
                "processed": 0, "skipped": 0, "failed": 0,
                "elapsed_seconds": 0,
            }

        for m in candidates:
            # Quota guard — her maç başına kontrol et
            current_used = current_quota_used(session)
            if current_used >= quota_stop:
                log.warning(
                    "quota stop: %d/%d (%.0f%%) — kalan %d maç ertesi güne",
                    current_used, quota_limit,
                    current_used / quota_limit * 100,
                    total_target - processed - failed,
                )
                break

            try:
                ingest_appearances_for_match(
                    session, src,
                    match_external_id=m.external_id, tenant_id=tenant_id,
                )
                session.commit()
                processed += 1
                if processed % 10 == 0:
                    log.info(
                        "ilerleme: %d/%d (quota: %d/%d)",
                        processed, total_target, current_used, quota_limit,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "match %d backfill başarısız: %s: %s",
                    m.external_id, type(e).__name__, e,
                )
                failed += 1
                session.rollback()

    elapsed = time.time() - started
    return {
        "candidates": total_target,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
    }
