"""SoccerTrack v2: takip çıktısı (DB tracking_frames) vs GT konumları — kare başına ofset + kapsama.

Veri setine özel doğrulama aracı. GT kare sayacı videoyla hizalı değil ve KAYIYOR
(ölçüldü: Δ −14 → −44 kare 90 sn'de); bu yüzden her karede küresel kestirim ±60
kare içinde ofset aranır. Rapor: GT→bizim ve bizim→GT en yakın komşu mesafeleri,
1.5 / 3 m eşikleri, kare başına oyuncu sayısı.

Kullanım (proje kökünden):
    venv-cv\\Scripts\\python.exe scripts/soccertrack_v2/validate_positions.py ^
        --match-id 990401 --start-minute 10 --sample-start 600 ^
        --gt-rows <klasör>/st_gt_rows_15k_25k.npy --database demo.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np

SEARCH_HALF_WINDOW = 60      # kare başına ofset araması (±kare)
GLOBAL_RANGE = range(-250, 251)


def nearest(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min(1)


def best_delta(gt_by: dict[int, np.ndarray], t: float, pts: np.ndarray, deltas) -> tuple[float, int, np.ndarray] | None:
    best = None
    for delta in deltas:
        g = gt_by.get(round(t * 25) + 1 + delta)
        if g is None:
            continue
        m = float(np.median(nearest(g, pts)))
        if best is None or m < best[0]:
            best = (m, delta, g)
    return best


def main() -> int:
    p = argparse.ArgumentParser(description="Takip konumları vs SoccerTrack v2 GT")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--start-minute", type=float, required=True)
    p.add_argument("--sample-start", type=float, required=True, help="örnek videonun yarı içindeki başlangıcı (sn)")
    p.add_argument("--gt-rows", type=Path, required=True)
    p.add_argument("--database", default="demo.db")
    args = p.parse_args()

    gt_by: dict[int, list[tuple[float, float]]] = {}
    for f, _xc, _yb, px, py in np.load(args.gt_rows):
        gt_by.setdefault(int(f), []).append((px + 52.5, py + 34.0))
    gt = {k: np.array(v) for k, v in gt_by.items()}

    c = sqlite3.connect(args.database)
    ours: list[tuple[float, np.ndarray]] = []
    q = "select minute, players_json from tracking_frames where match_external_id=? order by minute"
    for minute, pj in c.execute(q, (args.match_id,)):
        players = json.loads(pj) if pj else []
        pts = np.array([(pl["x"] / 100 * 105, pl["y"] / 100 * 68) for pl in players]) if players else np.zeros((0, 2))
        ours.append(((minute - args.start_minute) * 60.0 + args.sample_start, pts))
    print(f"bizim kare {len(ours)} · ort oyuncu/kare {np.mean([len(x) for _, x in ours]):.1f} (GT 22)")

    votes: dict[int, int] = {}
    for t, pts in ours[::10]:
        if len(pts) < 8:
            continue
        b = best_delta(gt, t, pts, GLOBAL_RANGE)
        if b:
            votes[b[1]] = votes.get(b[1], 0) + 1
    g0 = max(votes, key=lambda k: votes[k])
    print(f"küresel ofset kestirimi Δ≈{g0} kare")

    d_gt, d_us, deltas = [], [], []
    for t, pts in ours:
        if len(pts) < 8:
            continue
        b = best_delta(gt, t, pts, range(g0 - SEARCH_HALF_WINDOW, g0 + SEARCH_HALF_WINDOW + 1))
        if not b:
            continue
        _, delta, g = b
        deltas.append(delta)
        d_gt.append(nearest(g, pts))
        d_us.append(nearest(pts, g))
    dg, du = np.concatenate(d_gt), np.concatenate(d_us)
    print(f"GT→bizim: medyan {np.median(dg):.2f} m · ort {dg.mean():.2f} · <1.5 m %{(dg < 1.5).mean() * 100:.0f} "
          f"· <3 m %{(dg < 3).mean() * 100:.0f} (n={len(dg)})")
    print(f"bizim→GT: medyan {np.median(du):.2f} m · 3 m'den uzak (sahte/kenar) %{(du > 3).mean() * 100:.0f}")
    print(f"ofset dağılımı: min {min(deltas)} max {max(deltas)} · std {np.std(deltas):.1f} kare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
