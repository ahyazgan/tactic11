"""Snapshot diff CLI — geçmiş vs şu an.

Kullanım:
    python scripts/snapshot_diff.py --scope league:203:season:2024 --days 7
    python scripts/snapshot_diff.py --scope league:203:season:2024 --days 30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.snapshot import diff_snapshots, get_latest_snapshot, get_snapshot_at_or_before  # noqa: E402
from app.sports import football  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Snapshot diff — geçmiş vs şimdi")
    p.add_argument("--scope", required=True, help="örn: league:203:season:2024")
    p.add_argument("--days", type=int, default=7, help="kaç gün geriye bakılacak (default 7)")
    p.add_argument("--json", action="store_true", help="çıktıyı JSON olarak ver")
    args = p.parse_args()

    with SessionLocal() as session:
        latest = get_latest_snapshot(session, sport=football.SPORT_NAME, scope=args.scope)
        if latest is None:
            print(f"scope '{args.scope}' için snapshot yok.")
            sys.exit(1)
        baseline = get_snapshot_at_or_before(
            session,
            sport=football.SPORT_NAME,
            scope=args.scope,
            ts=latest.created_at - timedelta(days=args.days),
        )

    if baseline is None:
        print(f"baseline ({args.days} gün öncesi) bulunamadı.")
        print(f"en eski snapshot: {latest.created_at.isoformat()}")
        return

    if baseline.id == latest.id:
        print("baseline ve latest aynı — diff yok.")
        return

    diff = diff_snapshots(baseline, latest)
    if args.json:
        print(json.dumps({"scope": args.scope, **diff}, ensure_ascii=False, indent=2))
        return

    d = diff["delta"]
    print(f"scope: {args.scope}")
    print(f"  {baseline.created_at.isoformat()} → {latest.created_at.isoformat()}")
    print(f"  ({d['elapsed_seconds']/86400:.1f} gün geçti)")
    print()
    print(f"  leagues  : {baseline.leagues_count:>5} → {latest.leagues_count:<5}  (Δ {d['leagues_count']:+d})")
    print(f"  teams    : {baseline.teams_count:>5} → {latest.teams_count:<5}  (Δ {d['teams_count']:+d})")
    print(f"  matches  : {baseline.matches_count:>5} → {latest.matches_count:<5}  (Δ {d['matches_count']:+d})")


if __name__ == "__main__":
    main()
