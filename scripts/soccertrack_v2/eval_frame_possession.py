"""Takip karelerindeki sahiplik alanını (`possession_team_external_id`) dokunuş olaylarına karşı ölç (venv).

Maç raporunun faz ayrımı (topa sahipken / değilken şekil) bu alana dayanır. Referans
`eval_defending_events` ile aynıdır: aynı takımın ardışık iki dokunuşu arası (≤ 4 sn) top o
takımdadır; takım değiştiren aralıklar sayılmaz. Olay takımı → takip takımı eşlemenin
`team_side` alanından (taraf 0 = takip ev sahibi).

Ölçülenler: sahiplik aralığındaki karelerin kaçında alan dolu (kapsama), dolu olanların
kaçında doğru takım (isabet). Betimleyicidir; eşik ayarı yapmaz.

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_frame_possession \\
        --frames "data/tracking/live/990741/frames_ball/seg_*.json" \\
        --mapping docs/measurements/ball-events-mapping-132877.json --out sahiplik.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.soccertrack_v2.evaluate_ball_events import EventMapping, load_touches, possession_intervals


def score(frames: list[dict[str, Any]], intervals: list[tuple[float, float, int]], home: int, away: int) -> dict[str, Any]:
    """Kareler (minute, possession_team_external_id) ve olay aralıkları → kapsama ve isabet."""
    side_team = {0: home, 1: away}
    counts: Counter[str] = Counter()
    for f in frames:
        t = float(f["minute"]) * 60.0
        side = next((s for a, b, s in intervals if a <= t < b), None)
        if side is None:
            continue
        counts["in_possession"] += 1
        owner = f.get("possession_team_external_id")
        if owner is None:
            continue
        counts["labelled"] += 1
        counts["correct"] += owner == side_team[side]
    n, k = counts["in_possession"], counts["labelled"]
    return {**counts, "coverage": round(k / n, 3) if n else None,
            "accuracy": round(counts["correct"] / k, 3) if k else None}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True, help="frames JSON (glob)")
    p.add_argument("--mapping", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    payloads = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(args.frames))]
    home, away = payloads[0]["home_team_external_id"], payloads[0]["away_team_external_id"]
    frames = sorted((f for d in payloads for f in d["frames"]), key=lambda f: f["minute"])
    mapping = EventMapping.load(args.mapping)
    report = {"frames": args.frames, "mapping": str(args.mapping), "frames_total": len(frames),
              **score(frames, possession_intervals(load_touches(mapping), mapping.team_side), home, away)}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
