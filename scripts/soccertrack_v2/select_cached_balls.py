"""Replay candidate selection only; cached ROI searches retain their original anchor.

A positive result must be confirmed with a fresh end-to-end detector run before
rollout, because changing a selected ball also changes subsequent ROI searches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from scripts.soccertrack_v2.ball_selection_experiment import preferred_index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--appearance", choices=("any", "yellow"), required=True)
    args = p.parse_args()
    if args.out.exists():
        p.error("choose a new output directory")
    args.out.mkdir(parents=True)
    for path in sorted(args.cache.glob("seg_*.json")):
        payload = json.loads(path.read_text())
        cal = PitchCalibration.from_dict(payload["calibration"])
        changed = eligible_frames = 0
        for sample in payload["samples"]:
            candidates = [c for c in payload["candidates"][str(sample["order"]) ]
                          if c["confidence"] >= payload["config"]["ball_threshold"]
                          and cal.is_on_pitch((c["box"][0] + c["box"][2])/2, c["box"][3], margin_m=1)]
            confidence = [c["confidence"] for c in candidates]
            scores = [c["yellow_fraction"] for c in candidates] if args.appearance == "yellow" else None
            chosen = preferred_index(confidence, scores)
            if chosen is not None:
                eligible_frames += 1
                changed += chosen != preferred_index(confidence)
                c = candidates[chosen]
                x1, y1, x2, y2 = c["box"]
                sample["ball"] = [(x1+x2)/2, (y1+y2)/2, c["confidence"]]
                sample["ball_source"] = "det"
            elif sample["ball_source"] != "roi":
                sample["ball"] = sample["ball_source"] = None
        payload["selection_experiment"] = {"appearance": args.appearance, "changed": int(changed),
                                            "eligible_frames": eligible_frames,
                                            "roi_anchor_replayed": False}
        (args.out/path.name).write_text(json.dumps(payload), encoding="utf-8")
        print(path.name, payload["selection_experiment"])


if __name__ == "__main__":
    main()
