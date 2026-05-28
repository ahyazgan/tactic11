"""Backfill: tüm FT maçlar için lineup + player stats ingest.

`ingest_appearances_for_match`'i tüm bitmiş maçlara uygular. Quota-aware:
günlük API limitine yaklaşırsa durur, ertesi gün devam (idempotent — zaten
ingest edilmiş maçlar atlanır).

Kullanım:
    python scripts/backfill_appearances.py --tenant t-konya
    python scripts/backfill_appearances.py --tenant t-konya --limit 50 --dry-run

Çevre:
- USE_FIXTURES=true → tests/fixtures'tan okur (test/dev)
- USE_FIXTURES=false + API_FOOTBALL_KEY → gerçek API; her maç 2 call
  (lineups + players); günlük 7500 quota → ~3500 maç/gün cap

Idempotency:
- Hangi maçlar ingest edilmiş kontrol: player_appearances'ta `match_external_id`
  + `tenant_id` ile satır var mı?
- Varsa skip (force flag yoksa).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, setup_logging
from app.data.ingest import ingest_appearances_for_match
from app.data.sources.api_football import APIFootball
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

log = get_logger(__name__)

# Default quota guard: günlük limit'in %80'ine ulaşınca dur (Prompt 4 kuralı)
DEFAULT_QUOTA_FRACTION_STOP = 0.80


def _matches_to_backfill(
    session: Session, *,
    tenant_id: str | None,
    force: bool,
    limit: int | None,
) -> list[models.Match]:
    """Ingest edilecek maçları seç — FT + status finished + tenant filter."""
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

    # Ingest edilmemişleri filtrele
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


def _current_quota_used(session: Session, *, today_only: bool = True) -> int:
    from datetime import UTC, datetime
    stmt = select(func.count()).select_from(models.UsageEvent).where(
        models.UsageEvent.source == "api_football",
    )
    if today_only:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = stmt.where(models.UsageEvent.created_at >= start)
    return int(session.scalar(stmt) or 0)


def backfill(
    *, tenant_id: str,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    quota_stop_fraction: float = DEFAULT_QUOTA_FRACTION_STOP,
) -> dict[str, int]:
    """Backfill çalıştır + raporla."""
    from app.core.config import get_settings
    settings = get_settings()
    quota_limit = settings.api_football_daily_limit
    quota_stop = int(quota_limit * quota_stop_fraction)

    source = APIFootball()
    started = time.time()
    processed = skipped = failed = 0

    with SessionLocal() as session:
        # Tenant context — yeni satırlar bu tenant'a yazılsın
        session.info["tenant_id"] = tenant_id

        candidates = _matches_to_backfill(
            session, tenant_id=tenant_id, force=force, limit=limit,
        )
        total_target = len(candidates)
        log.info(
            "backfill başlıyor: tenant=%s candidates=%d limit=%s force=%s dry_run=%s",
            tenant_id, total_target, limit, force, dry_run,
        )
        if dry_run:
            return {
                "tenant_id_len": len(tenant_id),
                "candidates": total_target,
                "processed": 0, "skipped": 0, "failed": 0,
                "elapsed_seconds": 0,
            }

        for m in candidates:
            # Quota guard — her maç başına kontrol et
            current_used = _current_quota_used(session)
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
                    session, source,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Player appearance backfill")
    parser.add_argument("--tenant", required=True, help="tenant_id (UUID)")
    parser.add_argument("--limit", type=int, default=None, help="max maç sayısı")
    parser.add_argument(
        "--force", action="store_true",
        help="Zaten ingest edilmiş maçları da tekrar dene",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Aday maç sayısını yaz, ingest yapma",
    )
    parser.add_argument(
        "--quota-stop-fraction", type=float, default=DEFAULT_QUOTA_FRACTION_STOP,
        help="Quota bu fraksiyonu aşınca dur (default 0.80)",
    )
    args = parser.parse_args()

    setup_logging()
    report = backfill(
        tenant_id=args.tenant, limit=args.limit, force=args.force,
        dry_run=args.dry_run, quota_stop_fraction=args.quota_stop_fraction,
    )
    print()
    print("BACKFILL RAPOR")
    print("─" * 40)
    for k, v in report.items():
        print(f"  {k:.<28s} {v}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
