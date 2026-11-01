"""Top konumunu SoccerTrack olay konumlarına karşı ölç (117092 ilk yarı, venv).

Panoramada top GT'si yok; ama `117092_player_nodes.csv` her topa dokunuşta
dokunan oyuncunun saha konumunu verir. Dokunuş anında top o oyuncunun
ayağındadır. GSR'ye karşı doğrulandı (bkz. docs/TOP-TESPITI-OLAY-OLCUMU.md):

- Olay x/y ekseni yer değiştirmiş ve takıma göre normalize: x = genişlik,
  y = uzunluk; 30798 iki eksende ters, 9834 düz (yalnız bu maçın ilk yarısı).
- Zaman: GSR karesi = olay_ms·25/1000 + 3 → video saniyesi = olay_sn − 0,28
  (GSR karesi = round(t·25) + 1 + 9, `signal_quality_alignment.json`).
- Bu eşlemeyle olay konumu en yakın GSR oyuncusuna medyan 1,0 m, %85'i ≤ 2 m.

Ölçütler (frames JSON klasörleri; dakika alanı mutlak maç dakikası olmalı):

- **dokunuş**: olay anına en yakın karede (≤ `--window` sn) top olay konumuna
  ≤ `--radius` m → isabet; daha uzak → yanlış; top yok → kayıp.
- **uçuş**: başarılı kısa pasta (pasör → alıcı, 0,6–3 sn) zaman ortasında top,
  iki dokunuş konumu arasındaki doğru parçasına ≤ `--radius` m. Topu hep bir
  oyuncunun ayağına koyan yöntem dokunuşta kazanır ama burada kaybeder.

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_ball_events \\
        --frames data/tracking/live/990701/frames --out rapor.json
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

NODES = Path("data/tracking/datasets/soccertrack_v2/117092/117092_player_nodes.csv")
PITCH_L, PITCH_W = 105.0, 68.0
VIDEO_LAG_S = 0.28                      # video sn = olay sn − bu
FLIP = {"30798": True, "9834": False}   # takıma göre normalize eksenler (117092 ilk yarı)
GSR_TEAM = {"30798": 1, "9834": 0}      # olay takımı → GSR takımı (sol 0 / sağ 1), konumla eşlendi
PASS_MIN_S, PASS_MAX_S = 0.6, 3.0
POSSESSION_MAX_GAP_S = 4.0


@dataclass(frozen=True)
class Touch:
    t: float            # video saniyesi
    x: float            # metre, 0..105
    y: float            # metre, 0..68
    team: str
    types: str


def load_touches(path: Path = NODES) -> list[Touch]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["event_period"] != "FIRST_HALF" or not r["x"] or r["team_id"] not in FLIP:
                continue
            u, v = float(r["y"]), float(r["x"])  # eksenler yer değiştirmiş
            if FLIP[r["team_id"]]:
                u, v = 1.0 - u, 1.0 - v
            out.append(Touch(float(r["event_time"]) / 1000.0 - VIDEO_LAG_S, u * PITCH_L, v * PITCH_W,
                             r["team_id"], r["filtered_event_types"]))
    return sorted(out, key=lambda e: e.t)


def short_passes(touches: list[Touch]) -> list[tuple[Touch, Touch]]:
    """Başarılı kısa pas → takım arkadaşının sonraki dokunuşu."""
    pairs = []
    for a, b in zip(touches, touches[1:], strict=False):
        if ("passSucceeded" in a.types and "shortPass" in a.types and a.team == b.team
                and PASS_MIN_S <= b.t - a.t <= PASS_MAX_S):
            pairs.append((a, b))
    return pairs


def possession_intervals(touches: list[Touch], max_gap: float = POSSESSION_MAX_GAP_S,
                         ) -> list[tuple[float, float, int]]:
    """(başlangıç, bitiş, GSR takımı): aynı takımın ardışık iki dokunuşu arası — top o takımda.

    Takım değiştiren aralıklar (kayıp, kesme) belirsiz olduğu için alınmaz.
    """
    return [(a.t, b.t, GSR_TEAM[a.team]) for a, b in zip(touches, touches[1:], strict=False)
            if a.team == b.team and 0.0 < b.t - a.t <= max_gap]


def load_balls(dirs: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """(zamanlar sn, top metre [n,2] — top yoksa NaN), zamana göre sıralı."""
    ts, xy = [], []
    for d in dirs:
        for path in sorted(d.glob("seg_*.json")):
            for f in json.loads(path.read_text(encoding="utf-8"))["frames"]:
                ts.append(float(f["minute"]) * 60.0)
                b = f.get("ball")
                xy.append((b["x"] / 100.0 * PITCH_L, b["y"] / 100.0 * PITCH_W) if b else (np.nan, np.nan))
    order = np.argsort(ts)
    return np.asarray(ts)[order], np.asarray(xy, dtype=float).reshape(-1, 2)[order]


def segment_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    w = float(np.clip(np.dot(p - a, ab) / max(float(np.dot(ab, ab)), 1e-9), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + w * ab)))


def evaluate(ts: np.ndarray, balls: np.ndarray, touches: list[Touch], *, radius: float, window: float) -> dict[str, Any]:
    if not len(ts):
        return {"frames": 0}
    lo, hi = ts[0], ts[-1]

    def nearest(t: float) -> int | None:
        i = int(np.argmin(np.abs(ts - t)))
        return i if abs(ts[i] - t) <= window else None

    touch = {"hit": 0, "wrong": 0, "missing": 0}
    errors = []
    for e in touches:
        if not lo <= e.t <= hi or (i := nearest(e.t)) is None:
            continue
        if np.isnan(balls[i, 0]):
            touch["missing"] += 1
            continue
        d = float(np.hypot(balls[i, 0] - e.x, balls[i, 1] - e.y))
        errors.append(d)
        touch["hit" if d <= radius else "wrong"] += 1
    flight = {"hit": 0, "wrong": 0, "missing": 0}
    for a, b in short_passes(touches):
        tm = (a.t + b.t) / 2
        if not lo <= tm <= hi or (i := nearest(tm)) is None:
            continue
        if np.isnan(balls[i, 0]):
            flight["missing"] += 1
            continue
        d = segment_distance(balls[i], np.array([a.x, a.y]), np.array([b.x, b.y]))
        flight["hit" if d <= radius else "wrong"] += 1

    def rates(c: dict[str, int]) -> dict[str, Any]:
        n = sum(c.values())
        return {**c, "events": n, **{f"{k}_pct": round(100.0 * v / max(1, n), 1) for k, v in c.items()}}

    return {"frames": int(len(ts)), "ball_frame_pct": round(100.0 * float(np.mean(~np.isnan(balls[:, 0]))), 1),
            "touch": rates(touch), "flight": rates(flight),
            "touch_error_median_m": round(float(np.median(errors)), 2) if errors else None}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=Path, nargs="+", required=True, help="frames JSON klasörleri")
    p.add_argument("--nodes", type=Path, default=NODES)
    p.add_argument("--radius", type=float, default=3.0)
    p.add_argument("--window", type=float, default=0.2, help="olay ile kare arası en çok (sn)")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    ts, balls = load_balls(args.frames)
    report = {"frames_dirs": [str(d) for d in args.frames], "radius_m": args.radius, "window_s": args.window,
              **evaluate(ts, balls, load_touches(args.nodes), radius=args.radius, window=args.window)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
