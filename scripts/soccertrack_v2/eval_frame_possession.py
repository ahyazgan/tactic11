"""Takip karelerindeki sahiplik alanını (`possession_team_external_id`) dokunuş olaylarına karşı ölç (venv).

Raporun presi ve sahipliğe dayanan her analiz (faz ayrımı, geçiş anları) bu alana dayanır. Referans
`eval_defending_events` ile aynıdır: aynı takımın ardışık iki dokunuşu arası (≤ 4 sn) top o
takımdadır; takım değiştiren aralıklar sayılmaz. Olay takımı → takip takımı eşlemenin
`team_side` alanından (taraf 0 = takip ev sahibi).

Ölçülenler: sahiplik aralığındaki karelerin kaçında alan dolu (kapsama), dolu olanların
kaçında doğru takım (isabet). Ayrıca top kaybı anları: olaylarda farklı takımın ardışık iki
dokunuşu (≤ 4 sn) ikincisinin anında kayıptır; karelerde dolu sahiplik alanının takım
değiştirdiği an (araya giren boş kareler atlanır, ≤ 4 sn) kayıptır; ±`TOLERANCE_S` içinde
birebir eşleşme ile kesinlik ve duyarlılık. Betimleyicidir; eşik ayarı yapmaz.

`--window-s`: telestratörün kuralı (`app/tracking/telestration.py`, POSSESSION_WINDOW_S=1,0)
ile yeniden türetilmiş sahiplik: son round(pencere × fps) dolu oyun çoğunluğu (eşitlikte
penceredeki en eski), ilk oydan sonra her kareye yazılır. Ön kayıt (ölçümden önce): yalnız
1,0 sn denenir; top kaybı kesinliği >= %60 VE duyarlılık >= %50 ise faz ayrımı ve geçiş
anları yeniden sınanır, değilse yöntem elenir.

    venv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.eval_frame_possession \\
        --frames "data/tracking/live/990741/frames_ball/seg_*.json" \\
        --mapping docs/measurements/ball-events-mapping-132877.json --out sahiplik.json
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from scripts.soccertrack_v2.evaluate_ball_events import (
    POSSESSION_MAX_GAP_S,
    EventMapping,
    Touch,
    load_touches,
    possession_intervals,
)

TOLERANCE_S = 2.0


def event_turnovers(touches: list[Touch]) -> list[float]:
    return [b.t for a, b in zip(touches, touches[1:], strict=False)
            if a.team != b.team and 0.0 < b.t - a.t <= POSSESSION_MAX_GAP_S]


def frame_turnovers(frames: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    last: tuple[float, int] | None = None
    for f in frames:
        owner = f.get("possession_team_external_id")
        if owner is None:
            continue
        t = float(f["minute"]) * 60.0
        if last is not None and owner != last[1] and t - last[0] <= POSSESSION_MAX_GAP_S:
            out.append(t)
        last = (t, owner)
    return out


def match_times(found: list[float], truth: list[float], tolerance: float = TOLERANCE_S) -> dict[str, Any]:
    """Açgözlü birebir eşleşme (en yakın önce); kesinlik ve duyarlılık."""
    pairs = sorted((abs(a - b), i, j) for i, a in enumerate(found) for j, b in enumerate(truth) if abs(a - b) <= tolerance)
    used_f: set[int] = set()
    used_t: set[int] = set()
    for _d, i, j in pairs:
        if i not in used_f and j not in used_t:
            used_f.add(i)
            used_t.add(j)
    n = len(used_f)
    return {"found": len(found), "truth": len(truth), "matched": n,
            "precision": round(n / len(found), 3) if found else None,
            "recall": round(n / len(truth), 3) if truth else None}


def window_owners(frames: list[dict[str, Any]], window_s: float) -> list[dict[str, Any]]:
    """Telestratör kuralı: son round(window_s × fps) dolu oyun çoğunluğu her kareye."""
    times = [float(f["minute"]) * 60.0 for f in frames]
    steps = sorted(b - a for a, b in zip(times, times[1:], strict=False) if b > a)
    fps = 1.0 / steps[len(steps) // 2] if steps else 1.0
    votes: deque[int] = deque(maxlen=max(1, round(window_s * fps)))
    out: list[dict[str, Any]] = []
    for f in frames:
        owner = f.get("possession_team_external_id")
        if owner is not None:
            votes.append(owner)
        out.append({**f, "possession_team_external_id": Counter(votes).most_common(1)[0][0] if votes else None})
    return out


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
    p.add_argument("--window-s", type=float, default=0.0, help="0: ham alan; >0: telestratör pencere çoğunluğu")
    args = p.parse_args()
    payloads = [json.loads(Path(f).read_text(encoding="utf-8")) for f in sorted(glob.glob(args.frames))]
    home, away = payloads[0]["home_team_external_id"], payloads[0]["away_team_external_id"]
    frames = sorted((f for d in payloads for f in d["frames"]), key=lambda f: f["minute"])
    if args.window_s > 0:
        frames = window_owners(frames, args.window_s)
    mapping = EventMapping.load(args.mapping)
    touches = load_touches(mapping)
    lo, hi = float(frames[0]["minute"]) * 60.0, float(frames[-1]["minute"]) * 60.0
    truth = [t for t in event_turnovers(touches) if lo <= t <= hi]
    report = {"frames": args.frames, "mapping": str(args.mapping), "window_s": args.window_s,
              "frames_total": len(frames),
              **score(frames, possession_intervals(touches, mapping.team_side), home, away),
              "turnovers": {"tolerance_s": TOLERANCE_S, **match_times(frame_turnovers(frames), truth)}}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
