"""Measure a real fixed-camera pipeline without changing its decisions.

Preparation is separated from repeated warm runs. Nested detector and ReID
timings are descriptive components, not additive independent benchmarks.
No database is opened, no settings are tuned and existing outputs are refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.deepocsort import OSNetEmbedder
from app.tracking.detect import DetectorConfig, make_detector
from app.tracking.frames import frames_to_json
from app.tracking.pipeline import PipelineConfig, process_video


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tracker", choices=["supervision", "deepocsort", "consensus"], default="supervision")
    parser.add_argument("--seconds", type=float, default=10.)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, help="Explicit development detector batch; default keeps production configuration")
    parser.add_argument("--roi-single-batch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--capture-samples", action="store_true", help="Preserve dense player/ball evidence before output downsampling")
    args = parser.parse_args()
    if (args.out.exists() or args.runs < 2 or not 0 < args.seconds <= 30
            or (args.batch_size is not None and args.batch_size < 1)):
        parser.error("Fresh output, at least two runs and 0 < seconds <= 30 required")
    import torch

    cfg = PipelineConfig(max_seconds=args.seconds, tracker_backend=args.tracker,
        detector=DetectorConfig(model="small", weights="data/tracking/models/rfdetr_mixed_small", tiles=4,
            backend="torch", batch_size=args.batch_size, roi_single_batch=args.roi_single_batch))
    cal = PitchCalibration.load(args.calibration)
    paths = [args.video, args.calibration, Path(__file__)] + list(Path("app/tracking").rglob("*.py"))
    paths += [Path(cfg.detector.weights or "") / name for name in ("checkpoint_best_total.pth", "meta.json")]
    if args.tracker != "supervision":
        paths.append(Path(cfg.reid_model))
    hashes = {str(p): digest(p) for p in paths}
    start = perf_counter()
    detector = make_detector(cfg.detector)
    preparation_seconds = perf_counter() - start
    args.out.mkdir(parents=True)
    runs = []
    for run in range(args.runs):
        components = defaultdict(list)
        original_embedding = OSNetEmbedder.compute_embedding
        original_collect = pipeline.collect_observations
        collected = []

        def capture(*a, original_collect=original_collect, collected=collected, **kw):
            result = original_collect(*a, **kw)
            collected.append(result[0])
            return result

        class MeasuredDetector:
            def __init__(self, timings):
                self.timings = timings
                self.ball_ids = detector.ball_ids

            def detect(self, rgb):
                start = perf_counter()
                result = detector.detect(rgb)
                self.timings[f"detect_{rgb.shape[1]}x{rgb.shape[0]}"].append(perf_counter() - start)
                return result

            def split(self, result):
                return detector.split(result)

            def predict_single(self, rgb):
                start = perf_counter()
                result = detector.predict_single(rgb)
                self.timings[f"roi_{rgb.shape[1]}x{rgb.shape[0]}"].append(perf_counter() - start)
                return result

        def embedding(self, *a, components=components, original_embedding=original_embedding, **kw):
            start = perf_counter()
            result = original_embedding(self, *a, **kw)
            components["reid_embedding"].append(perf_counter() - start)
            return result

        start = perf_counter()
        with (patch.object(OSNetEmbedder, "compute_embedding", embedding),
              patch.object(pipeline, "collect_observations", side_effect=capture) if args.capture_samples else nullcontext()):
            frames, summary = process_video(args.video, cal, cfg=cfg, detector=MeasuredDetector(components),
                match_id=990905, home_team_id=217, away_team_id=213)
        seconds = perf_counter() - start
        payload = frames_to_json(frames, match_id=990905)
        serialized = json.dumps(payload, sort_keys=True).encode()
        (args.out / f"run_{run}.frames.json").write_bytes(serialized)
        (args.out / f"run_{run}.summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        sample_hash = None
        if args.capture_samples:
            if len(collected) != 1:
                raise ValueError("Expected exactly one observation collection per run")
            keys = ("order", "frame_idx", "seconds", "persons", "ball", "ball_source", "continuity_id", "person_teams")
            dense = json.dumps([{key: getattr(s, key) for key in keys} for s in collected[0]], sort_keys=True).encode()
            (args.out / f"run_{run}.samples.json").write_bytes(dense)
            sample_hash = hashlib.sha256(dense).hexdigest()
        runs.append(dict(run=run, pipeline_seconds=seconds, source_seconds=args.seconds,
            realtime_factor=seconds / args.seconds, output_sha256=hashlib.sha256(serialized).hexdigest(),
            frames=len(frames), sampled_frames=summary["sampled_frames"],
            sample_output_sha256=sample_hash,
            roi_model_prepared=getattr(detector, "_roi_model", None) is not None,
            components={name: dict(calls=len(values), total_seconds=sum(values),
                mean_ms=1000 * float(np.mean(values)), p95_ms=1000 * float(np.percentile(values, 95)))
                for name, values in components.items()}))
        print(json.dumps(runs[-1]), flush=True)
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Input or code changed during profiling")
    report = dict(scope=__doc__, config=asdict(cfg), preparation_seconds=preparation_seconds,
        device=torch.cuda.get_device_name() if torch.cuda.is_available() else "CPU", python=platform.python_version(),
        hashes=hashes, runs=runs, repeated_output_equal=len({r["output_sha256"] for r in runs}) == 1,
        limitations="Local hardware; no preview or database; first pipeline run may include tracker/model initialization. GPU must be otherwise idle.")
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
