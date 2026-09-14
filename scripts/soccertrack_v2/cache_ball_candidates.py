"""Cache every ball candidate before winner selection, with reversible colour evidence.

Uses the existing production detector/tracker. No ground-truth event coordinates
are loaded and no database is written. Segments must be chosen before evaluation.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, make_detector
from app.tracking.pipeline import PipelineConfig, collect_observations
from app.tracking.teams import torso_color
from scripts.soccertrack_v2.ball_selection_experiment import yellow_fraction


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--segments", type=int, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--source", type=Path, default=Path("data/tracking/live/990401"))
    p.add_argument("--calibration", type=Path, default=Path("data/tracking/calibrations/soccertrack_v2_117092.json"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if any((args.out / f"seg_{s:04d}.json").exists() for s in args.segments):
        p.error("choose fresh segments/output; existing evidence must not be overwritten")
    cfg = PipelineConfig(detector=DetectorConfig(model="small", weights="data/tracking/models/rfdetr_mixed_small", tiles=4))
    detector = make_detector(cfg.detector)
    cal = PitchCalibration.load(args.calibration)
    candidates = {}
    detected_persons = {}
    def capture(rgb, detections, sample):
        persons, balls = detector.split(detections)
        people = []
        for box, confidence in zip(persons.xyxy, persons.confidence, strict=True):
            color = torso_color(rgb, tuple(map(float, box)))
            people.append({"box": list(map(float, box)), "confidence": float(confidence),
                           "color": color.tolist() if color is not None else None})
        detected_persons[sample.order] = people
        rows = []
        for box, confidence in zip(balls.xyxy, balls.confidence, strict=True):
            x1, y1, x2, y2 = map(float, box)
            rows.append({"box": [x1, y1, x2, y2], "confidence": float(confidence),
                         "yellow_fraction": yellow_fraction(rgb, box),
                         "on_pitch": cal.is_on_pitch((x1+x2)/2, y2, margin_m=1)})
        candidates[sample.order] = rows
    for seg in args.segments:
        candidates.clear()
        detected_persons.clear()
        start = time.perf_counter()
        samples, teams, stats = collect_observations(args.source / f"seg_{seg:04d}.mp4", cfg,
                                                    detector=detector, calib=cal, observation_hook=capture)
        payload = {"segment": seg, "samples": [asdict(s) for s in samples], "candidates": dict(candidates),
                   "detected_persons": dict(detected_persons),
                   "colors": {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()},
                   "config": asdict(cfg), "calibration": cal.to_dict(), "stats": stats,
                   "elapsed_seconds": time.perf_counter() - start}
        (args.out / f"seg_{seg:04d}.json").write_text(json.dumps(payload), encoding="utf-8")
        print(f"saved {seg}: {payload['elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
