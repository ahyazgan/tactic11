"""StatsBomb Open event ingest CLI — match'leri DB'ye yaz.

Production'da bu script:
1. matches tablosundaki belirli maç(lar)ı (tenant + league + season filtreli) bul
2. Her maç için StatsBomb Open Data GitHub'dan events çek
3. ingest_events_for_match çağır (idempotent — varsa skip)
4. Özet rapor: maç sayısı / event sayısı / hata

Kullanım:
    # Tek maç
    python -m scripts.ingest_statsbomb_events --tenant t-default --match 3754066

    # Bir takımın son 10 maçı (events tablosunda olmayanlar)
    python -m scripts.ingest_statsbomb_events --tenant t-default --team 611 --limit 10

    # Sadece dry-run (hangi maçlar atılacak göster, ingest etme)
    python -m scripts.ingest_statsbomb_events --tenant t-default --team 611 --dry-run

Notlar:
- StatsBomb Open Data ücretsiz, kota sınırı yok (GitHub raw); cache ile yine de
  konservatif çağrı (her maç 1 HTTP).
- Bu script multi-tenant: --tenant parametresi zorunlu.
- Tüm event'ler EventRow tablosuna multi-tenant safe yazılır.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.data.ingest.event import ingest_events_for_match
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

log = get_logger(__name__)


def _candidate_matches(
    session, *, tenant_id: str,
    team_id: int | None = None,
    match_id: int | None = None,
    limit: int | None = None,
) -> list[models.Match]:
    """İngest adayı maçları seç.

    Filtreler:
    - tenant_id (loader criteria zaten uyguluyor, ama explicit netlik)
    - team_id verildiyse: home veya away
    - match_id verildiyse: tek maç
    - status FINISHED
    - events tablosunda zaten ingest edilmemiş olanlar (idempotent dış katman)
    """
    stmt = select(models.Match).where(
        models.Match.sport == football.SPORT_NAME,
        models.Match.status.in_(football.FINISHED_STATUSES),
    )
    if match_id is not None:
        stmt = stmt.where(models.Match.external_id == match_id)
    elif team_id is not None:
        stmt = stmt.where(
            (models.Match.home_team_external_id == team_id)
            | (models.Match.away_team_external_id == team_id),
        )
    stmt = stmt.order_by(models.Match.kickoff.desc())
    if limit:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars())


def _already_ingested(session, match_external_id: int, tenant_id: str) -> bool:
    cnt = session.scalar(
        select(models.EventRow).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.tenant_id == tenant_id,
            models.EventRow.match_external_id == match_external_id,
        ).limit(1)
    )
    return cnt is not None


def ingest(
    *, tenant_id: str,
    team_id: int | None = None,
    match_id: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """İngest çalıştır + raporla."""
    source = StatsBombOpen()
    started = time.time()
    processed = skipped = failed = total_events = 0
    failures: list[dict[str, Any]] = []

    with SessionLocal() as session:
        session.info["tenant_id"] = tenant_id

        candidates = _candidate_matches(
            session, tenant_id=tenant_id,
            team_id=team_id, match_id=match_id, limit=limit,
        )
        total = len(candidates)
        log.info(
            "ingest başlıyor: tenant=%s candidates=%d team=%s match=%s "
            "limit=%s dry_run=%s force=%s",
            tenant_id, total, team_id, match_id, limit, dry_run, force,
        )

        if dry_run:
            return {
                "tenant_id": tenant_id, "candidates": total,
                "processed": 0, "skipped": 0, "failed": 0,
                "events_written": 0,
                "elapsed_seconds": 0,
                "dry_run_match_ids": [m.external_id for m in candidates],
            }

        for m in candidates:
            mid = m.external_id
            if not force and _already_ingested(session, mid, tenant_id):
                skipped += 1
                log.info("match=%d zaten ingest edilmiş, skip", mid)
                continue
            try:
                report = ingest_events_for_match(
                    session, source,
                    match_external_id=mid, tenant_id=tenant_id,
                )
                session.commit()
                processed += 1
                total_events += report.rows_inserted
                log.info(
                    "match=%d ingest OK — inserted=%d skipped=%d "
                    "(shots=%d passes=%d carries=%d def=%d)",
                    mid, report.rows_inserted, report.rows_skipped,
                    report.shots, report.passes, report.carries,
                    report.defensive_actions,
                )
            except Exception as e:  # noqa: BLE001 - script-level catch
                session.rollback()
                failed += 1
                failures.append({"match_id": mid, "error": str(e)[:200]})
                log.warning("match=%d ingest FAIL: %s", mid, e)

    return {
        "tenant_id": tenant_id,
        "candidates": total,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "events_written": total_events,
        "failures": failures,
        "elapsed_seconds": round(time.time() - started, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="StatsBomb Open Data event ingest (Faz N storage)",
    )
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--team", type=int, default=None,
                        help="Sadece bu takımın maçları")
    parser.add_argument("--match", type=int, default=None,
                        help="Sadece bu maç (StatsBomb match_id)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max kaç maç işle (sıralı en yeni → eski)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Hangi maçlar atılacak göster, ingest etme")
    parser.add_argument("--force", action="store_true",
                        help="Zaten ingest edilmiş maçları da yeniden çağır "
                             "(idempotent — yine de skip yapar event seviyesinde)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    report = ingest(
        tenant_id=args.tenant, team_id=args.team, match_id=args.match,
        limit=args.limit, dry_run=args.dry_run, force=args.force,
    )
    print("\n=== Ingest Report ===")
    for k, v in report.items():
        if k == "failures" and v:
            print(f"  {k}:")
            for f in v[:5]:
                print(f"    - match {f['match_id']}: {f['error']}")
        elif k == "dry_run_match_ids":
            print(f"  {k}: {v[:10]}{'...' if len(v) > 10 else ''} (total {len(v)})")
        else:
            print(f"  {k}: {v}")
    return 0 if report.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
