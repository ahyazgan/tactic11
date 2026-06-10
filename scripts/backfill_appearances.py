"""Backfill: tüm FT maçlar için lineup + player stats ingest (CLI sarmalayıcı).

Çekirdek mantık `app.data.ingest.backfill` modülünde — scheduler job'ı ve
`sync_league.py --appearances` da aynı çekirdeği kullanır. Quota-aware:
günlük API limitine yaklaşırsa durur, ertesi gün devam (idempotent — zaten
ingest edilmiş maçlar atlanır).

Kullanım:
    python scripts/backfill_appearances.py --tenant t-konya
    python scripts/backfill_appearances.py --tenant t-konya --limit 50 --dry-run

Çevre:
- USE_FIXTURES=true → tests/fixtures'tan okur (test/dev)
- USE_FIXTURES=false + API_FOOTBALL_KEY → gerçek API; her maç 2 call
  (lineups + players)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.logging import setup_logging  # noqa: E402
from app.data.ingest.backfill import (  # noqa: E402
    DEFAULT_QUOTA_FRACTION_STOP,
    backfill_appearances,
)


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
    report = backfill_appearances(
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
