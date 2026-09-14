"""Cache identical detector/tracker observations for team-assignment comparisons.

Run as a module with venv-cv Python. Local caches contain source paths and config;
existing files are rejected to avoid overwriting evidence from another run.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig, make_detector
from app.tracking.pipeline import PipelineConfig, collect_observations


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--segments", type=int, nargs="+", default=[0, 3, 6, 9])
    p.add_argument("--source", type=Path, default=Path("data/tracking/live/990401"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--calibration", type=Path, default=Path("data/tracking/calibrations/soccertrack_v2_117092.json"))
    p.add_argument("--weights", default="data/tracking/models/rfdetr_mixed_small")
    color = p.add_mutually_exclusive_group()
    color.add_argument("--raw-kit-colors", action="store_true", help="raw kit colours (default; retained for old commands)")
    color.add_argument("--normalize-kit-light", action="store_true", help="experimental local field-light normalization")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for seg in args.segments:
        if (args.out / f"seg_{seg:04d}.json").exists():
            p.error(f"cache exists: segment {seg}")
    cfg = PipelineConfig(detector=DetectorConfig(model="small", weights=args.weights, tiles=4),
                         normalize_kit_light=args.normalize_kit_light)
    detector = make_detector(cfg.detector)
    calib = PitchCalibration.load(args.calibration)
    for seg in args.segments:
        video = args.source / f"seg_{seg:04d}.mp4"
        samples, teams, stats = collect_observations(video, cfg, detector=detector, calib=calib)
        payload = {"video": str(video), "segment": seg, "config": asdict(cfg),
                   "calibration": calib.to_dict(), "stats": stats,
                   "samples": [asdict(s) for s in samples],
                   "colors": {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()}}
        (args.out / f"seg_{seg:04d}.json").write_text(json.dumps(payload), encoding="utf-8")
        print(f"cached segment {seg}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
