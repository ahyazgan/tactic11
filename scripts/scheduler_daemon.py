"""Scheduler daemon CLI — kayıtlı job'ları günlük saatlerde koşturur.

Kullanım:
    python scripts/scheduler_daemon.py                # sürekli (Ctrl+C ile dur)
    python scripts/scheduler_daemon.py --once         # tek tarama (cron modu)
    python scripts/scheduler_daemon.py --interval 60  # tick aralığı (sn)

Zamanlamayı SCHEDULER_SCHEDULE env'i ile özelleştir (bkz. .env.example).
Her koşu job_runs tablosuna yazılır → /admin/jobs ekranından izlenir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.scheduler.daemon import run_daemon  # noqa: E402

log = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="tactic11 scheduler daemon")
    parser.add_argument("--interval", type=int, default=30, help="Tick aralığı, saniye")
    parser.add_argument("--once", action="store_true", help="Tek tarama yap ve çık (cron modu)")
    args = parser.parse_args()

    setup_logging()
    try:
        run_daemon(interval_seconds=args.interval, once=args.once)
    except KeyboardInterrupt:
        log.info("scheduler daemon durduruldu (Ctrl+C)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
