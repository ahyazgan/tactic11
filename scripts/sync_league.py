"""Bir lig + sezon için adapter'dan veri çek, doğrula, DB'ye yaz.

Kullanım:
    python scripts/sync_league.py --league 203 --season 2024

USE_FIXTURES=true ise gerçek API yerine tests/fixtures'tan okur.
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
from app.data.ingest import sync_league  # noqa: E402
from app.data.sources.api_football import APIFootball  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lig sync (Faz 1)")
    parser.add_argument("--league", type=int, required=True, help="API-Football league.id")
    parser.add_argument("--season", type=int, required=True, help="Sezon yılı, örn. 2024")
    parser.add_argument("--last", type=int, default=10, help="Takım başına son N maç")
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


if __name__ == "__main__":
    main()
