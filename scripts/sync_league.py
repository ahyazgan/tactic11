"""Bir lig + sezon için adapter'dan veri çek, doğrula, DB'ye yaz.

Kullanım:
    python scripts/sync_league.py --league 203 --season 2024
    # Sync + biten maçların kadro/istatistik ingest'i tek komutta:
    python scripts/sync_league.py --league 203 --season 2025 --appearances 30

USE_FIXTURES=true ise gerçek API yerine tests/fixtures'tan okur.
--appearances N: sync sonrası en yeni N bitmiş maç için lineup + player-stats
ingest (quota-aware, idempotent). Oyuncu sezon istatistiği ve özellik (1-20)
türetimi bu veriden beslenir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Proje kökünü sys.path'e ekle ki `python scripts/...` doğrudan çalışsın.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.data.ingest import backfill_appearances, sync_league  # noqa: E402
from app.data.sources.api_football import APIFootball  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.db.tenant_context import DEFAULT_TENANT_ID  # noqa: E402

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lig sync (Faz 1)")
    parser.add_argument("--league", type=int, required=True, help="API-Football league.id")
    parser.add_argument("--season", type=int, required=True, help="Sezon yılı, örn. 2024")
    parser.add_argument("--last", type=int, default=10, help="Takım başına son N maç")
    parser.add_argument(
        "--appearances", type=int, default=0,
        help="Sync sonrası en yeni N bitmiş maç için lineup+stats ingest (0=kapalı)",
    )
    parser.add_argument(
        "--tenant", default=DEFAULT_TENANT_ID,
        help=f"Appearance ingest tenant_id (default: {DEFAULT_TENANT_ID})",
    )
    args = parser.parse_args()

    setup_logging()
    source = APIFootball()
    with SessionLocal() as session:
        report = sync_league(
            session,
            source,
            league_id=args.league,
            season=args.season,
            matches_per_team=args.last,
        )

    log.info(
        "sync tamam: leagues=%d teams=%d matches=%d rejected=%d snapshot=%d",
        report.leagues_written,
        report.teams_written,
        report.matches_written,
        report.rejected_count,
        report.snapshot_id,
    )

    if args.appearances > 0:
        bf = backfill_appearances(
            tenant_id=args.tenant, limit=args.appearances, source=source,
        )
        log.info(
            "appearance ingest tamam: candidates=%s processed=%s failed=%s",
            bf["candidates"], bf["processed"], bf["failed"],
        )


if __name__ == "__main__":
    main()
