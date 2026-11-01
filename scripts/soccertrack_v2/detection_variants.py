"""Dedektör çalışma ayarı varyantlarıyla ham gözlem önbelleği (venv-cv).

Dondurulmuş takip kodu değiştirilmez: `collect_observations` yalnız farklı
`DetectorConfig` (dilim sayısı, güven eşiği, çözünürlük) ile çağrılır. Çıktı
`cache_observations` biçimindedir; `detection_audit` ile ölçülür. Segment başına
duvar saati süresi de yazılır (canlı mod için 30 sn'lik segment bütçesi).

    venv-cv\\Scripts\\python.exe -X utf8 -m scripts.soccertrack_v2.detection_variants \\
        --segments 1 5 9 --tiles 6 --threshold 0.35 --out data/tracking/bench/det_t6
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--segments", type=int, nargs="+", required=True)
    p.add_argument("--source", type=Path, default=Path("data/tracking/live/990401"))
    p.add_argument("--calibration", type=Path, default=Path("data/tracking/calibrations/soccertrack_v2_117092.json"))
    p.add_argument("--weights", default="data/tracking/models/rfdetr_mixed_small")
    p.add_argument("--tiles", type=int, default=4)
    p.add_argument("--threshold", type=float, default=0.35)
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for seg in args.segments:
        if (args.out / f"seg_{seg:04d}.json").exists():
            p.error(f"önbellek var: segment {seg}")
    detector_cfg = DetectorConfig(model="small", weights=args.weights, tiles=args.tiles,
                                  threshold=args.threshold, resolution=args.resolution)
    cfg = PipelineConfig(detector=detector_cfg)
    detector = make_detector(detector_cfg)
    calib = PitchCalibration.load(args.calibration)
    for seg in args.segments:
        video = args.source / f"seg_{seg:04d}.mp4"
        started = time.perf_counter()
        samples, teams, stats = collect_observations(video, cfg, detector=detector, calib=calib)
        elapsed = time.perf_counter() - started
        payload = {"video": str(video), "segment": seg, "config": asdict(cfg), "calibration": calib.to_dict(),
                   "stats": stats, "elapsed_seconds": round(elapsed, 1),
                   "samples": [asdict(s) for s in samples],
                   "colors": {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()}}
        (args.out / f"seg_{seg:04d}.json").write_text(json.dumps(payload), encoding="utf-8")
        print(f"segment {seg}: {elapsed:.1f} sn", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
