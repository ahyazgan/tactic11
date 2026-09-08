"""StatsBomb 360 freeze-frame ingest — saha overlay'i için pozisyon verisi.

Bir maç için sırayla:
1. matches satırı yoksa StatsBomb'dan seed et (La Liga sezonları taranır)
2. events yoksa ingest et (source_event_id = StatsBomb uuid — 360 ile birleşir)
3. player_appearances yoksa doldur (replay kadro farkındalığı)
4. 360 freeze frame'leri events ile birleştirip tracking_frames'e yaz

Kullanım:
    python -m scripts.ingest_statsbomb_360 --tenant t-default --match 3773672
    python -m scripts.ingest_statsbomb_360 --tenant t-default --match 3773672 --replace

360 verisi yalnız bazı yarışmalarda var (competitions.json → match_available_360).
Barcelona–Sevilla 1-1 (La Liga 2020/21, 3773672) demo için seçildi: rakip
16029 ile aynı, demo takım eşlemesi bozulmaz.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy import select

from app.core.logging import get_logger
from app.data.ingest.event import ingest_events_for_match
from app.data.ingest.tracking import delete_match_frames, ingest_tracking_match
from app.data.sources.statsbomb_360 import StatsBomb360Adapter, StatsBomb360Error
from app.data.sources.statsbomb_open import StatsBombOpen
from app.db import models
from app.db.session import SessionLocal
from app.sports import football

log = get_logger(__name__)

DEFAULT_MATCH_ID = 3773672  # Barcelona 1-1 Sevilla, La Liga 2020/21 (360 var)


def ingest_360(*, tenant_id: str, match_id: int, replace: bool = False) -> dict:
    from app.db.base import Base
    from app.db.session import engine
    from scripts.demo_real_statsbomb import _ingest_appearances, _seed_match_from_statsbomb
    from scripts.dev_seed import _sync_missing_columns

    Base.metadata.create_all(engine)
    _sync_missing_columns(engine)

    started = time.time()
    src = StatsBombOpen()
    report: dict = {"tenant_id": tenant_id, "match_id": match_id}

    with SessionLocal() as session:
        session.info["tenant_id"] = tenant_id

        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
                models.Match.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if match is None:
            seeded = _seed_match_from_statsbomb(session, match_id=match_id, tenant_id=tenant_id)
            session.commit()
            report["match_seeded"] = True
            home_id, away_id, kickoff = (
                seeded.home_team_external_id, seeded.away_team_external_id, seeded.kickoff,
            )
        else:
            report["match_seeded"] = False
            home_id, away_id, kickoff = (
                match.home_team_external_id, match.away_team_external_id, match.kickoff,
            )

        events = src.get_events(match_id)

        has_events = session.execute(
            select(models.EventRow.id).where(
                models.EventRow.sport == football.SPORT_NAME,
                models.EventRow.tenant_id == tenant_id,
                models.EventRow.match_external_id == match_id,
            ).limit(1)
        ).first()
        if has_events is None:
            ev_report = ingest_events_for_match(
                session, src, match_external_id=match_id, tenant_id=tenant_id,
            )
            session.commit()
            report["events_inserted"] = ev_report.rows_inserted
        else:
            report["events_inserted"] = 0

        has_app = session.execute(
            select(models.PlayerAppearance.id).where(
                models.PlayerAppearance.match_external_id == match_id,
                models.PlayerAppearance.tenant_id == tenant_id,
            ).limit(1)
        ).first()
        if has_app is None:
            n = _ingest_appearances(
                session, src, match_id=match_id, tenant_id=tenant_id, kickoff=kickoff,
            )
            session.commit()
            report["appearances_inserted"] = n
        else:
            report["appearances_inserted"] = 0

        if replace:
            removed = delete_match_frames(
                session, sport=football.SPORT_NAME, match_external_id=match_id,
            )
            report["frames_removed"] = removed

        adapter = StatsBomb360Adapter(
            events=events, home_team_id=home_id, away_team_id=away_id,
        )
        try:
            tr = ingest_tracking_match(
                session, adapter, match_external_id=match_id, sport=football.SPORT_NAME,
            )
        except StatsBomb360Error as e:
            session.rollback()
            report["error"] = str(e)
            return report
        session.commit()
        report["frames_written"] = tr.frames_written
        report["frames_updated"] = tr.frames_updated

    report["elapsed_seconds"] = round(time.time() - started, 2)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="StatsBomb 360 freeze-frame ingest")
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--match", type=int, default=DEFAULT_MATCH_ID,
                        help=f"StatsBomb match_id (varsayılan {DEFAULT_MATCH_ID})")
    parser.add_argument("--replace", action="store_true",
                        help="Maçın mevcut frame'lerini silip baştan yaz")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    report = ingest_360(tenant_id=args.tenant, match_id=args.match, replace=args.replace)
    print("\n=== 360 Ingest Report ===")
    for k, v in report.items():
        print(f"  {k}: {v}")
    return 1 if "error" in report else 0


if __name__ == "__main__":
    sys.exit(main())
