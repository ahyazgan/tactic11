"""Tahmin backtest CLI — predict v3 + kalibrasyon T'nin gerçek-veri kazancı.

frontend/src/lib/match-results.json (gerçek maç sonuçları) üzerinde walk-forward
backtest çalıştırır ve baseline vs v3 + kalibrasyon karşılaştırmasını basar.

Kullanım:
    python -m scripts.predict_backtest [--comp fr.1] [--season 1718] [--limit N]
    python -m scripts.predict_backtest --all          # tüm lig/sezonları birleştir
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.engine.backtest.harness import MatchRow, run_backtest

DATA = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "match-results.json"


def _load(comp: str | None, season: str | None, limit: int | None) -> list[MatchRow]:
    raw = json.loads(DATA.read_text())
    rows = []
    for r in raw:
        if comp and r.get("comp") != comp:
            continue
        if season and r.get("season") != season:
            continue
        try:
            rows.append(MatchRow(
                date=r["date"], home=r["home"], away=r["away"],
                hg=int(r["hg"]), ag=int(r["ag"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda x: x.date)
    if limit:
        rows = rows[:limit]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", default="fr.1")
    ap.add_argument("--season", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--all", action="store_true", help="tüm lig/sezon")
    args = ap.parse_args()

    comp = None if args.all else args.comp
    rows = _load(comp, args.season, args.limit)
    print(f"Yüklenen maç: {len(rows)} (comp={comp or 'ALL'}, season={args.season or 'ALL'})")

    cmp = run_backtest(rows)

    print("\n=== Model karşılaştırması (düşük Brier/log-loss = iyi) ===")
    hdr = f"{'model':<34} {'N':>6} {'Brier':>8} {'logloss':>8} {'ECE':>7} {'acc':>7}"
    print(hdr)
    print("-" * len(hdr))
    for m in (cmp.baseline, cmp.v3):
        print(f"{m.label:<34} {m.n:>6} {m.brier:>8.4f} {m.log_loss:>8.4f} {m.ece:>7.4f} {m.accuracy:>7.4f}")

    db, dv = cmp.baseline, cmp.v3
    if db.log_loss and dv.log_loss:
        d_ll = (db.log_loss - dv.log_loss) / db.log_loss * 100
        d_br = (db.brier - dv.brier) / db.brier * 100
        print(f"\nv3 kazanç: log-loss {d_ll:+.2f}% · Brier {d_br:+.2f}% (pozitif = iyileşme)")

    if cmp.calibration:
        c = cmp.calibration
        d = (c.log_loss_raw - c.log_loss_calibrated) / c.log_loss_raw * 100 if c.log_loss_raw else 0.0
        print(f"\n=== Kalibrasyon (train→test, N_test={c.n_test}) ===")
        print(f"  öğrenilen T = {c.temperature}")
        print(f"  log-loss: ham {c.log_loss_raw:.4f} → kalibre {c.log_loss_calibrated:.4f} ({d:+.2f}%)")
    else:
        print("\nKalibrasyon: yeterli örneklem yok (train<20).")


if __name__ == "__main__":
    main()
