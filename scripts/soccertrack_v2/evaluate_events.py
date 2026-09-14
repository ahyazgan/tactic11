"""Read-only video event/coverage audit against SoccerTrack's 12-class labels.

Temporal coincidences are NOT event precision: source clocks, team identity and
pass recipients have not been independently validated. No database writes.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

PASS_LABELS = {"PASS", "HIGH PASS", "CROSS"}


def temporal_matches(predicted: list[float], reference: list[float], tolerance: float) -> int:
    """One-to-one temporal matches; one reference can never validate two predictions."""
    if not predicted or not reference:
        return 0
    d = np.abs(np.asarray(predicted)[:, None] - np.asarray(reference)[None, :])
    penalty = (len(predicted) + len(reference) + 1) * (tolerance + 1)
    i, j = linear_sum_assignment(np.where(d <= tolerance, d, penalty))
    return int(np.sum(d[i, j] <= tolerance))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--start-seconds", type=float, default=600)
    p.add_argument("--end-seconds", type=float, default=960)
    p.add_argument("--period", type=int, choices=(1,), default=1,
                   help="this audit uses the first-half video/event clock")
    args = p.parse_args()
    if not 0 <= args.start_seconds < args.end_seconds:
        p.error("expected 0 <= start-seconds < end-seconds")
    frames, passes, defenses = [], [], []
    rejected: Counter = Counter()
    for path in sorted(args.frames.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        frames.extend(f for f in payload["frames"] if f["period"] == args.period
                      and args.start_seconds <= f["minute"] * 60 < args.end_seconds)
        passes.extend(x for x in payload.get("derived_passes", [])
                      if args.start_seconds <= x["minute"] * 60 < args.end_seconds)
        defenses.extend(x for x in payload.get("derived_defensive_actions", [])
                        if args.start_seconds <= x["minute"] * 60 < args.end_seconds)
        rejected.update(payload.get("summary", {}).get("passes", {}).get("rejected", {}))
    actions = json.loads(args.events.read_text(encoding="utf-8"))["actions"]
    actions = [a for a in actions if a["gameTime"].startswith(f"{args.period} -")
               and args.start_seconds <= float(a["position"]) / 1000 < args.end_seconds]
    times = [float(a["position"]) / 1000 for a in actions if a["label"] in PASS_LABELS]
    predicted = [a["minute"] * 60 for a in passes]
    n = len(frames)
    if not n:
        p.error("no video frames in the requested interval")
    report = {
        "period": args.period, "start_seconds": args.start_seconds, "end_seconds": args.end_seconds,
        "frames": n, "video_pass_attempts": len(passes),
        "video_completed_passes": sum(p.get("complete", True) for p in passes),
        "video_defensive_actions": len(defenses),
        "gt_pass_attempts": len(times), "gt_event_counts": dict(Counter(a["label"] for a in actions)),
        "frames_with_ball_ratio": sum(f.get("ball") is not None for f in frames) / n if n else 0,
        "frames_with_observed_ball_ratio": sum(f.get("ball") is not None and not f.get("ball_estimated") for f in frames) / n if n else 0,
        "frames_with_actor_ratio": sum(any(p.get("is_actor") for p in f["players"]) for f in frames) / n if n else 0,
        "pass_rejections_full_segments": dict(rejected),
        "temporal_coincidences": {f"within_{t}s": temporal_matches(predicted, times, t) for t in (1, 2, 3)},
        "limitation": "Temporal coincidences alone are not precision/recall; clock alignment, team and recipient correctness remain unverified.",
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
