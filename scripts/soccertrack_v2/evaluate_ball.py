"""Top tespiti ölçümleri (venv-cv): TeamTrack gerçek top etiketleri ve SoccerTrack olaylarına bağlı oran.

- `teamtrack`: `teamtrack_mixed/test` dilimlerinde (gerçek top kutusu) modelin top
  bulma oranı ve kesinliği; merkez uzaklığı ≤ 12 px eşleşme, dilimsiz çıkarım.
- `events`: bir `cache_observations`/`detection_variants` önbelleğinde, SoccerTrack
  12 sınıf olaylarından oyunda olanların (pas, top sürme, şut…) ±0,2 sn içinde
  top tespiti olan olay oranı ve top tespitli kare oranı. Panoramada top GT'si
  yok; olay anında top kesin oyundadır.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_ball teamtrack \\
        --weights data/tracking/models/rfdetr_mixed_small
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.evaluate_ball events \\
        --cache data/tracking/bench/det_t4_c0.35
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

IN_PLAY = {"PASS", "DRIVE", "HIGH PASS", "CROSS", "SHOT", "HEADER", "BALL PLAYER BLOCK", "PLAYER SUCCESSFUL TACKLE"}
MATCH_PX = 12.0
EVENT_WINDOW_S = 0.2
DELTA_FRAMES = 9


def match_balls(pred: list[tuple[float, float]], gt: list[tuple[float, float]]) -> tuple[int, int, int]:
    """(tp, fn, fp): her GT topu en yakın kullanılmamış tahmine ≤ MATCH_PX."""
    used: set[int] = set()
    tp = 0
    for g in gt:
        d = [np.hypot(p[0] - g[0], p[1] - g[1]) if i not in used else np.inf for i, p in enumerate(pred)]
        if d and min(d) <= MATCH_PX:
            used.add(int(np.argmin(d)))
            tp += 1
    return tp, len(gt) - tp, len(pred) - len(used)


def event_rate(cache: Path, events_path: Path, start_seconds: float) -> dict:
    data = json.loads(events_path.read_text(encoding="utf-8"))
    events = [float(a["position"]) / 1000 for a in data["actions"]
              if a["gameTime"].startswith("1 -") and a["label"] in IN_PLAY]
    hit = total = frames = ball_frames = 0
    for path in sorted(glob.glob(str(cache / "seg_*.json"))):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        seg = payload["segment"]
        ts = np.array([start_seconds + seg * 30 + s["seconds"] for s in payload["samples"]])
        has = np.array([bool(s.get("ball")) and s.get("ball_source") == "det" for s in payload["samples"]])
        frames += len(has)
        ball_frames += int(has.sum())
        for e in events:
            t = e - (1 + DELTA_FRAMES) / 25  # GT karesi = round(t·25) + 1 + delta
            if len(ts) and ts[0] <= t <= ts[-1]:
                total += 1
                hit += bool(has[np.abs(ts - t) <= EVENT_WINDOW_S].any())
    return {"cache": str(cache), "in_play_events": total, "events_with_ball": hit,
            "event_ball_rate": round(hit / max(1, total), 4), "frames": frames,
            "ball_frame_share": round(ball_frames / max(1, frames), 4)}


def teamtrack(weights: str, root: Path) -> dict:
    import cv2

    from app.tracking.detect import DetectorConfig, make_detector

    ann = json.loads((root / "_annotations.coco.json").read_text(encoding="utf-8"))
    balls: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for a in ann["annotations"]:
        if a["category_id"] == 2:
            x, y, w, h = a["bbox"]
            balls[a["image_id"]].append((x + w / 2, y + h / 2))
    det = make_detector(DetectorConfig(model="small", weights=weights, tiles=1, threshold=0.35))
    tp = fn = fp = 0
    for im in ann["images"]:
        rgb = cv2.cvtColor(cv2.imread(str(root / im["file_name"])), cv2.COLOR_BGR2RGB)
        _persons, b = det.split(det.detect(rgb))
        pred = [((x1 + x2) / 2, (y1 + y2) / 2) for x1, y1, x2, y2 in b.xyxy]
        a, c, d = match_balls(pred, balls.get(im["id"], []))
        tp, fn, fp = tp + a, fn + c, fp + d
    return {"weights": weights, "images": len(ann["images"]), "tp": tp, "fn": fn, "fp": fp,
            "recall": round(tp / max(1, tp + fn), 4), "precision": round(tp / max(1, tp + fp), 4)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    t = sub.add_parser("teamtrack")
    t.add_argument("--weights", required=True)
    t.add_argument("--split", type=Path, default=Path("data/tracking/datasets/teamtrack_mixed/test"))
    e = sub.add_parser("events")
    e.add_argument("--cache", type=Path, required=True)
    e.add_argument("--events", type=Path,
                   default=Path("data/tracking/datasets/soccertrack_v2/117092/117092_12_class_events.json"))
    e.add_argument("--start-seconds", type=float, default=600.0)
    for q in (t, e):
        q.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    report = teamtrack(args.weights, args.split) if args.mode == "teamtrack" else \
        event_rate(args.cache, args.events, args.start_seconds)
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
