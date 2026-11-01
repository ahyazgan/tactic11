"""Dokunuş olaylarını videoya bağlayan eşlemeyi takip edilen OYUNCULARDAN bul (venv).

GSR'si olmayan maçta (ör. 132877) `evaluate_ball_events --mapping` için gerekli
eşleme: takıma göre eksen çevirmesi ve video zaman kayması. Yalnız oyuncu
konumları kullanılır; top ve sahiplik sonuçlarına bakılmaz, yani eşleme ölçümü
etkilemez. Ölçüt: dokunuş anında olay konumuna ≤ 2 m takip edilen oyuncu bulunan
dokunuş payı (117092'de GSR'ye karşı bulunan eşleme aynı yolla doğrulanabilir).

Başlangıç kayması `padding_info.csv`'den: video sn = olay sn + Padding/1000.

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.derive_event_mapping \\
        --frames data/tracking/live/990741/frames --nodes .../132877_player_nodes.csv \\
        --padding .../132877_padding_info.csv --out docs/measurements/ball-events-mapping-132877.json
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.soccertrack_v2.evaluate_ball_events import PITCH_L, PITCH_W, EventMapping, load_touches

NEAR_M = 2.0


def first_half_padding_s(path: Path) -> float:
    with path.open(encoding="utf-8") as fh:
        row = next(r for r in csv.DictReader(fh) if r["Event Period"] == "FIRST_HALF")
    return float(row["Padding"]) / 1000.0 - float(row["Start Match Time"]) / 1000.0


def load_players(dirs: list[Path]) -> tuple[np.ndarray, list[np.ndarray], list[list[int | None]]]:
    ts, xy, teams = [], [], []
    for d in dirs:
        for path in sorted(d.glob("seg_*.json")):
            for f in json.loads(path.read_text(encoding="utf-8"))["frames"]:
                ts.append(float(f["minute"]) * 60.0)
                xy.append(np.array([(p["x"] / 100 * PITCH_L, p["y"] / 100 * PITCH_W) for p in f["players"]],
                                   dtype=float).reshape(-1, 2))
                teams.append([p.get("team_external_id") for p in f["players"]])
    order = np.argsort(ts)
    return np.asarray(ts)[order], [xy[i] for i in order], [teams[i] for i in order]


def near_share(mapping: EventMapping, ts: np.ndarray, xy: list[np.ndarray]) -> tuple[float, int]:
    near = n = 0
    for e in load_touches(mapping):
        if not ts[0] <= e.t <= ts[-1]:
            continue
        i = int(np.argmin(np.abs(ts - e.t)))
        if abs(ts[i] - e.t) > 0.2 or not len(xy[i]):
            continue
        n += 1
        near += float(np.min(np.hypot(xy[i][:, 0] - e.x, xy[i][:, 1] - e.y))) <= NEAR_M
    return (near / n if n else 0.0), n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", type=Path, nargs="+", required=True)
    p.add_argument("--nodes", type=Path, required=True)
    p.add_argument("--padding", type=Path, default=None, help="padding_info.csv (başlangıç kayması)")
    p.add_argument("--base-offset", type=float, default=None, help="padding dosyası yoksa başlangıç kayması (sn)")
    p.add_argument("--search-s", type=float, default=2.0, help="kayma araması ± (sn)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    ts, xy, teams = load_players(args.frames)
    with args.nodes.open(encoding="utf-8") as fh:
        team_ids = sorted({r["team_id"] for r in csv.DictReader(fh) if r["event_period"] == "FIRST_HALF"})
    if (args.padding is None) == (args.base_offset is None):
        p.error("--padding ya da --base-offset (yalnız biri)")
    base = first_half_padding_s(args.padding) if args.padding is not None else args.base_offset
    results = []
    for flips in itertools.product((False, True), repeat=len(team_ids)):
        for off in np.arange(-args.search_s, args.search_s + 1e-9, 0.2):
            m = EventMapping(args.nodes, dict(zip(team_ids, flips, strict=True)), base + float(off),
                             dict.fromkeys(team_ids, 0))
            share, n = near_share(m, ts, xy)
            results.append((share, n, flips, round(float(off), 2)))
    results.sort(key=lambda r: -r[0])
    share, n, flips, off = results[0]
    mapping = EventMapping(args.nodes, dict(zip(team_ids, flips, strict=True)), base + off, dict.fromkeys(team_ids, 0))
    # olay takımı → takip ev sahibi (0) / deplasman (1): dokunan oyuncunun takip takımı çoğunluğu
    votes: Counter[tuple[str, int | None]] = Counter()
    for e in load_touches(mapping):
        if not ts[0] <= e.t <= ts[-1]:
            continue
        i = int(np.argmin(np.abs(ts - e.t)))
        if not len(xy[i]):
            continue
        d = np.hypot(xy[i][:, 0] - e.x, xy[i][:, 1] - e.y)
        j = int(np.argmin(d))
        if d[j] <= NEAR_M:
            votes[(e.team, teams[i][j])] += 1
    tracked = sorted({t for _, t in votes if t is not None})
    side = {}
    for team in team_ids:
        best = max(tracked, key=lambda t, team=team: votes[(team, t)]) if tracked else None
        side[team] = tracked.index(best) if best is not None else 0
    report = {"nodes": str(args.nodes).replace("\\", "/"), "flip": dict(zip(team_ids, flips, strict=True)),
              "video_offset_s": round(base + off, 3), "team_side": side,
              "derived_from": "tracked player positions only (no ball, no possession)",
              "padding_base_s": base, "offset_search_best_s": off, "near_share": round(share, 3),
              "touches_used": n, "second_best": [list(r[:2]) + [list(r[2]), r[3]] for r in results[1:4]],
              "team_votes": {f"{a}->{b}": v for (a, b), v in sorted(votes.items(), key=lambda kv: -kv[1])}}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
