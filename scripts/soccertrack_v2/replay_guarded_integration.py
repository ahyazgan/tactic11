"""Real RGB/OSNet production replay against the completed 19-clip candidate.

Only person detector outputs are cached. Frame decoding, colors, three trackers,
filtering, retrospective partitions, output frames and event derivation are real.
This is development parity, not fresh control or detector speed measurement.
"""
from __future__ import annotations

import argparse
import gc
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.deepocsort import DEFAULT_MODEL
from app.tracking.detect import DetectorConfig
from app.tracking.frames import frames_to_json
from scripts.soccertrack_v2.benchmark_deepocsort import VIDEO_DIRS
from scripts.soccertrack_v2.benchmark_guarded_identity import known_configurations
from scripts.soccertrack_v2.benchmark_tracker_backends import digest, load
from scripts.soccertrack_v2.short_gap_replay_cache import local_path
from scripts.soccertrack_v2.validate_palette_acquisition import validate_group


def comparison_rows(rows):
    return json.loads(json.dumps([{k: s[k] for k in
        ("order", "frame_idx", "seconds", "continuity_id", "persons", "person_teams")} for s in rows]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--group", choices=list(known_configurations()))
    parser.add_argument("--segment", type=int)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    import cv2
    import supervision as sv
    import torch

    if version("supervision") != "0.30.2" or version("trackers") != "2.6.0":
        parser.error("Measured tracker versions required")
    cv2.setNumThreads(1)
    torch.set_grad_enabled(False)
    acquisition = [validate_group(g) for g in ("day", "night")]
    prior_path = args.expected / "report.json"
    prior = load(prior_path)
    acceptance = prior["development_acceptance"]
    if not prior.get("completed_at_utc") or not all(acceptance[k] for k in
            ("old_boundaries_pass", "source_coverage_pass", "sparse_regressions_pass")):
        raise ValueError("Completed accepted development reference required")
    original_inputs = {local_path(p).resolve(): sha for p, sha in prior["input_code_sha256"].items()}
    original_outputs = {local_path(p).resolve(): sha for p, sha in prior["output_sha256"].items()}
    hashes = {}

    def remember(path, registry=None):
        sha = digest(path)
        if registry is not None and registry.get(path.resolve()) != sha:
            raise ValueError(f"Reference evidence missing or changed: {path}")
        hashes[str(path)] = sha

    remember(prior_path)
    remember(Path(DEFAULT_MODEL), original_inputs)
    for path in [Path(__file__), *Path("app/tracking").rglob("*.py")]:
        remember(path)
    configs = {g: cfg for g, cfg in known_configurations().items() if args.group in (None, g)}
    cases = []
    for group, config in configs.items():
        for segment in config["segments"]:
            if args.segment is not None and args.segment != segment:
                continue
            raw_path = Path(config["cache"]) / f"seg_{segment:04d}.json"
            raw = load(raw_path)
            video = (local_path(raw["video"]) if "video" in raw
                     else Path(VIDEO_DIRS[group]) / f"seg_{segment:04d}.mp4")
            anchor_path = Path("docs/measurements") / f"{config['anchor']}.json"
            expected_path = args.expected / group / "combined" / f"seg_{segment:04d}.json"
            baseline_path = args.expected / group / "baseline" / f"seg_{segment:04d}.json"
            for path in (raw_path, video, anchor_path):
                remember(path, original_inputs)
            for path in (expected_path, baseline_path):
                remember(path, original_outputs)
            cases.append((group, segment, raw_path, video, anchor_path, expected_path, baseline_path))
    if not cases:
        parser.error("No selected known clips")
    args.out.mkdir(parents=True)
    report = dict(started_at_utc=datetime.now(UTC).isoformat(), scope=__doc__,
                  acquisition=acquisition, input_code_sha256=hashes, comparisons=[], output_sha256={},
                  versions={n: version(n) for n in ("supervision", "trackers", "numpy", "scipy", "torch", "filterpy")},
                  decoder_threads=1, secondary_inference="fresh source RGB and pinned OSNet on every clip",
                  new_control_opened=False)
    (args.out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2 if path.name.endswith("report.json") else None) + "\n", encoding="utf-8")
        report["output_sha256"][str(path)] = digest(path)

    original_capture = cv2.VideoCapture

    def single_thread_capture(path):
        cap = original_capture(path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        if not cap.isOpened() or cap.get(cv2.CAP_PROP_N_THREADS) != 1:
            cap.release()
            raise ValueError("Single-thread source decoder required")
        return cap

    for group, segment, raw_path, video, anchor_path, expected_path, baseline_path in cases:
        raw = load(raw_path)
        anchor = np.asarray(load(anchor_path)["anchors"]["before"])
        config = pipeline.PipelineConfig(**{k: v for k, v in raw["config"].items() if k != "detector"})
        config.detector = DetectorConfig(**raw["config"]["detector"])
        config.tracker_backend = "guarded"
        config.refine_player_identities = False
        config.preview_path = None
        calibration = PitchCalibration.from_dict(raw["calibration"])

        class CachedDetector:
            def __init__(self, source):
                self.position = 0
                self.source = source

            def detect(self, rgb):
                sample = self.source["samples"][self.position]
                self.position += 1
                people = self.source["detected_persons"][str(sample["order"])]
                return sv.Detections(xyxy=np.asarray([p["box"] for p in people]).reshape(-1, 4),
                    confidence=np.asarray([p["confidence"] for p in people]), class_id=np.zeros(len(people), dtype=int))

            def split(self, detections):
                return detections, sv.Detections.empty()

        detector = CachedDetector(raw)
        collected, baseline = [], []
        original_collect = pipeline.collect_observations

        def capture(*a, original_collect=original_collect, baseline=baseline, anchor=anchor,
                    collected=collected, **kw):
            samples, assigner, stats = original_collect(*a, **kw)
            baseline.extend(asdict(s) for s in samples)
            assignment = assigner.fit(anchor, eligible_tracks={p[0] for s in samples for p in s.persons})
            for sample in baseline:
                sample["person_teams"] = {str(p[0]): assignment.team_by_track.get(p[0]) for p in sample["persons"]}
            collected.extend(samples)
            return samples, assigner, stats

        started = perf_counter()
        with patch.object(cv2, "VideoCapture", side_effect=single_thread_capture), patch.object(
                pipeline, "collect_observations", side_effect=capture):
            frames, summary = pipeline.process_video(video, calibration, cfg=config, detector=detector,
                team_anchor=anchor, match_id=991010, home_team_id=217, away_team_id=213)
        if detector.position != len(raw["samples"]):
            raise ValueError("Incomplete source decoding")
        samples = [asdict(s) for s in collected]
        baseline_equal = comparison_rows(baseline) == comparison_rows(load(baseline_path)["samples"])
        equal = comparison_rows(samples) == comparison_rows(load(expected_path)["samples"])
        target = args.out / group / f"seg_{segment:04d}.json"
        write(target, dict(samples=samples, summary=summary))
        write(target.with_suffix(".frames.json"), frames_to_json(frames, match_id=991010))
        report["comparisons"].append(dict(group=group, segment=segment, baseline_equal=baseline_equal,
            equal=equal, observations=sum(len(s["persons"]) for s in samples), frames=len(frames),
            elapsed_seconds=perf_counter() - started, identity_guarded=summary["calibration_stats"]["identity_guarded"]))
        write(args.out / "partial-report.json", {k: v for k, v in report.items() if k != "output_sha256"})
        print(group, segment, "baseline equal:", baseline_equal, "combined equal:", equal, flush=True)
        if not equal or not baseline_equal:
            raise ValueError("Production output differs from completed research reference")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Inputs or production code changed during replay")
    report.update(completed_at_utc=datetime.now(UTC).isoformat(), all_equal=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
