"""Çapa+takip sınavı (venv-cv). Ön kayıt: docs/measurements/broadcast-tracking-preregistration.json.

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam run --match kyoto_kobe --out <klasör>
    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.broadcast_track_exam gates --dir <klasör>

Elle çapa verilmez, sistem çapayı kendisi bulur. Görüntüler repoda değildir.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from scripts.calibration_funnel import MATCH_GROUP, other_frames, video_of
from scripts.tracking_funnel import mark_errors

FPS = 15.0
SAMPLE_EVERY = 45           # 3 sn: shot_exam örnek aralığı
END_OFFSET = 44             # tracking_funnel uç karesi
MAX_SAMPLES = 120
START_POINTS = Path("docs/measurements/daylight-calibration-truth-points.json")
END_POINTS = Path("docs/measurements/tracking-funnel-end-truth-points.json")
D1_MIN_MAIN = 0.60
D2_MAX_MEDIAN_M = 2.0
WRONG_M = 5.0
D2_MAX_WRONG = 0.05
D3_MAX_OTHER = 0.05


def timed_frames(video: Path) -> Iterator[tuple[int, np.ndarray]]:
    """(15 fps ızgara no, kare): sıralı okur, her kareyi aramaz."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"video açılamadı: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    index = 0
    try:
        for k in range(MAX_SAMPLES * SAMPLE_EVERY):
            target = int(round(k / FPS * fps))
            frame = None
            while index <= target:
                ok, frame = cap.read()
                index += 1
                if not ok:
                    return
            yield k, frame
    finally:
        cap.release()


def marked_frames(match: str) -> dict[int, list[dict]]:
    """15 fps ızgara no → el noktaları: klip başı ve klip sonu işaretleri."""
    marks: dict[int, list[dict]] = {}
    for path, offset in ((START_POINTS, 0), (END_POINTS, END_OFFSET)):
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"].get(match, {})
        for sample, spec in frames.items():
            if spec.get("points"):
                marks[int(sample) * SAMPLE_EVERY + offset] = spec["points"]
    return marks


def run(match: str, out: Path) -> int:
    from app.tracking.broadcast_track import BackfillingTracker, TrackFrame

    if MATCH_GROUP.get(match) != "development":
        print(f"{match}: geliştirme maçı değil", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    others = other_frames(match)
    marks = marked_frames(match)
    tracker = BackfillingTracker(FPS)
    states: Counter = Counter()
    kept: dict[int, TrackFrame] = {}
    produced: set[int] = set()
    total = 0
    size = (0, 0)
    start = time.perf_counter()
    for k, frame in timed_frames(video_of(match)):
        size = (frame.shape[1], frame.shape[0])
        total += 1
        for done_k, result in tracker.feed(k, frame):
            states[result.state] += 1
            if result.homography is not None:
                produced.add(done_k)
            if done_k % SAMPLE_EVERY == 0 or done_k in marks:
                kept[done_k] = result
        if k % 450 == 0:
            print(match, k, dict(states), flush=True)
    seconds = time.perf_counter() - start
    samples, evidence = [], []
    for k in sorted(kept):
        result = kept[k]
        if k % SAMPLE_EVERY == 0:
            i = k // SAMPLE_EVERY
            samples.append({"sample": i, "label": "other" if i in others else "main",
                            "posed": result.homography is not None, "state": result.state})
        if k in marks and result.homography is not None:
            errors = mark_errors(result.homography, marks[k])
            evidence.append({"k": k, "median_m": round(float(np.median(errors)), 2),
                             "worst_m": round(float(errors.max()), 2), "state": result.state})
    record = {"match": match, "frames": total, "produced": len(produced), "states": dict(states), "size": size,
              "seconds": round(seconds, 1), "samples": samples, "evidence": evidence,
              "marked_frames": len(marks)}
    (out / f"{match}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return 0


def evaluate(records: list[dict]) -> dict:
    samples = [s for r in records for s in r["samples"]]
    main = [s for s in samples if s["label"] == "main"]
    other = [s for s in samples if s["label"] == "other"]
    evidence = [e for r in records for e in r["evidence"]]
    medians = [e["median_m"] for e in evidence]
    wrong = sum(m > WRONG_M for m in medians)
    main_rate = sum(s["posed"] for s in main) / len(main) if main else 0.0
    other_rate = sum(s["posed"] for s in other) / len(other) if other else 0.0
    median = float(np.median(medians)) if medians else None
    wrong_rate = wrong / len(medians) if medians else None
    return {
        "per_match": {r["match"]: {
            "main_posed": sum(s["posed"] for s in r["samples"] if s["label"] == "main"),
            "main": sum(s["label"] == "main" for s in r["samples"]),
            "other_posed": sum(s["posed"] for s in r["samples"] if s["label"] == "other"),
            "other": sum(s["label"] == "other" for s in r["samples"]),
            "frames": r["frames"], "produced": r["produced"], "states": r["states"],
            "fps": round(r["frames"] / r["seconds"], 2) if r["seconds"] else None,
        } for r in records},
        "main_posed": sum(s["posed"] for s in main), "main": len(main), "main_rate": round(main_rate, 3),
        "other_posed": sum(s["posed"] for s in other), "other": len(other), "other_rate": round(other_rate, 3),
        "marked_produced": len(medians), "marked_total": sum(r["marked_frames"] for r in records),
        "median_m": median, "wrong_over_5m": wrong,
        "worst_median_m": max(medians) if medians else None,
        "D1": main_rate >= D1_MIN_MAIN,
        "D2": median is not None and median <= D2_MAX_MEDIAN_M and wrong_rate is not None and wrong_rate <= D2_MAX_WRONG,
        "D3": other_rate <= D3_MAX_OTHER,
    }


def gates(folder: Path) -> int:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    result = evaluate(records)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print("evidence", [(r["match"][:5], e["k"], e["median_m"], e["worst_m"], e["state"]) for r in records for e in r["evidence"]])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--match", required=True)
    r.add_argument("--out", type=Path, required=True)
    g = sub.add_parser("gates")
    g.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args()
    return run(args.match, args.out) if args.cmd == "run" else gates(args.dir)


if __name__ == "__main__":
    sys.exit(main())
