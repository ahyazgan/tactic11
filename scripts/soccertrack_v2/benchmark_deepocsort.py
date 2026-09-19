"""Pinned Deep OC-SORT appearance/motion ablation on known source videos."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from app.tracking.deepocsort import (
    DEFAULT_MODEL,
    MODEL_SHA256,
    PROFILE,
    DeepOCSortTracker,
    OSNetEmbedder,
)
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    MEASUREMENTS,
    EvidenceTracker,
    adjudicated_rows,
    backend_settings,
    box_key,
    digest,
    groups,
    load,
    pair_subset,
    predictions,
    regressions,
    retrack,
    score_pairs,
    score_rows,
    source_boxes,
)
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    replay as baseline_replay,
)

BACKENDS = ("supervision", "deepocsort_motion", "deepocsort")
VIDEO_DIRS = {
    "day": "data/tracking/bench/daylight_117093/source",
    "night": "data/tracking/live/990401",
    "night_extra": "data/tracking/bench/perimeter_control_night/source",
    "night_old_control": "data/tracking/bench/joint_identity_control/source",
}


class VideoReplay:
    def __init__(self, tracker, video, samples):
        import cv2
        self.tracker = tracker
        self.cap = cv2.VideoCapture(str(video))
        if not self.cap.isOpened():
            raise ValueError(f"Cannot open {video}")
        self.samples = iter(samples)
        self.frame = -1
        self.max_time_lost = tracker.max_time_lost
        self.update_seconds = []

    def update_with_detections(self, detections):
        sample = next(self.samples)
        wanted = sample["frame_idx"]
        if wanted <= self.frame:
            raise ValueError("Source frames must be strictly increasing")
        while self.frame < wanted:
            ok, bgr = self.cap.read()
            if not ok:
                raise ValueError("Source video ended before source detection frame")
            self.frame += 1
        start = perf_counter()
        result = self.tracker.update_with_detections(detections, bgr)
        self.update_seconds.append(perf_counter() - start)
        return result


def replay(data, backend, anchor, video):
    if backend == "supervision":
        return baseline_replay(data, backend, anchor)
    import supervision as sv
    settings = backend_settings(data, "supervision")
    lost = int(settings["frame_rate"] / 30 * settings["lost_track_buffer"])
    tracker = DeepOCSortTracker(threshold=settings["track_activation_threshold"], lost_frames=lost,
        embedder=OSNetEmbedder(DEFAULT_MODEL) if backend == "deepocsort" else None,
        appearance=backend == "deepocsort")
    stream = VideoReplay(tracker, video, data["samples"])
    wrapped = EvidenceTracker(stream, external=False)
    try:
        with patch.object(sv, "ByteTrack", return_value=wrapped):
            samples, teams, stats = retrack(data, correct_buffer=False)
    finally:
        stream.cap.release()
    assignment = teams.fit(anchor, eligible_tracks={p[0] for s in samples for p in s.persons})
    for sample in samples:
        sample.person_teams = {str(p[0]): assignment.team_by_track.get(p[0]) for p in sample.persons}
    stats.update(profile=PROFILE, appearance=tracker.appearance, model_sha256=MODEL_SHA256 if tracker.appearance else None,
                 settings=dict(threshold=tracker.threshold, lost_frames=lost, min_hits=1,
                               iou=.3, delta_t=3, inertia=.2, weight=.75, alpha=.95, aw=.5,
                               cmc=False, grid=False, new_kf=False, adaptive_appearance=tracker.appearance),
                 tracking_update_ms={"mean": 1000 * float(np.mean(stream.update_seconds)),
                                     "p95": 1000 * float(np.percentile(stream.update_seconds, 95)),
                                     "frames": len(stream.update_seconds)},
                 observations=sum(len(s.persons) for s in samples),
                 tracks=len({p[0] for s in samples for p in s.persons}))
    return {"samples": [asdict(s) for s in samples]}, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("fresh output directory required")
    if version("trackers") != "2.6.0" or version("supervision") != "0.30.2":
        parser.error("frozen trackers==2.6.0 and supervision==0.30.2 required")
    import trackers

    package = Path(trackers.__file__).parent
    paths = [Path(__file__), Path("scripts/soccertrack_v2/benchmark_track_buffer.py"),
             Path("scripts/soccertrack_v2/benchmark_joint_identity.py")]
    paths += list(Path("app/tracking").rglob("*.py"))
    paths += [Path(DEFAULT_MODEL), Path("scripts/soccertrack_v2/benchmark_tracker_backends.py")]
    paths += [Path(VIDEO_DIRS[g]) / f"seg_{s:04d}.mp4" for g,c in groups().items() for s in c["segments"]]
    paths += list(package.rglob("*.py"))
    configs = groups()
    for cfg in configs.values():
        paths += [Path(cfg["cache"]) / f"seg_{s:04d}.json" for s in cfg["segments"]]
        paths += [MEASUREMENTS / f"{name}.json" for name in cfg["labels"] + cfg["pairs"] + [cfg["anchor"]]]
    paths += [MEASUREMENTS / f"{n}.json" for n in (
        "identity-kit-label-adjudication", "duplicate-part-development-labels",
        "joint-identity-control-day-labels")]
    hashes = {str(p): digest(p) for p in paths}
    args.out.mkdir(parents=True)
    manifest = {"started_at_utc": datetime.now(UTC).isoformat(), "input_code_sha256": hashes,
                "versions": {n: version(n) for n in ("trackers", "supervision", "numpy", "scipy", "filterpy", "torch")},
                "groups": configs, "scope": "All previously seen data is development; no new control opened"}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {}
    for group, cfg in configs.items():
        inputs = {s: load(Path(cfg["cache"]) / f"seg_{s:04d}.json") for s in cfg["segments"]}
        available = source_boxes(inputs)
        anchor = np.asarray(load(MEASUREMENTS / f"{cfg['anchor']}.json")["anchors"]["before"])
        rows = [r for name in cfg["labels"] for r in load(MEASUREMENTS / f"{name}.json")["records"]]
        excluded = set()
        if group == "day":
            rows = adjudicated_rows(rows, [load(MEASUREMENTS / "identity-kit-label-adjudication.json")])
            parts = load(MEASUREMENTS / "duplicate-part-development-labels.json")["records"]
            old_control = load(MEASUREMENTS / "joint-identity-control-day-labels.json")
            old_pairs = load(MEASUREMENTS / "joint-identity-control-day-pairs.json")
            parts += [r for r in old_pairs["observations"] if r.get("duplicate_part_of")]
            excluded = {(r["segment"], box_key(r["frame_idx"], r["bbox"])) for r in parts}
            rows += old_control["records"]
            rows = [r for r in rows if (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in excluded]
        if any((r["segment"], box_key(r["frame_idx"], r["bbox"])) not in available for r in rows):
            raise ValueError("kit annotation not present in source boxes")
        result[group] = {}
        for backend in BACKENDS:
            payloads, stats = {}, {}
            for segment, data in inputs.items():
                payloads[segment], stats[segment] = replay(data, backend, anchor, Path(VIDEO_DIRS[group]) / f"seg_{segment:04d}.mp4")
                target = args.out / group / backend
                target.mkdir(parents=True, exist_ok=True)
                (target / f"seg_{segment:04d}.json").write_text(json.dumps(payloads[segment]) + "\n", encoding="utf-8")
                print(group, backend, segment, stats[segment]["observations"], flush=True)
            pair_scores = {name: score_pairs(pair_subset(load(MEASUREMENTS / f"{name}.json"), excluded),
                                            payloads, available) for name in cfg["pairs"]}
            if any(s["source_unmatched_observations"] for s in pair_scores.values()):
                raise ValueError("pair annotation not present in source boxes")
            result[group][backend] = dict(kit=score_rows(rows, predictions(payloads), blue=0),
                                          pairs=pair_scores, segments=stats)
    decisions = {}
    for backend in BACKENDS[1:]:
        failures = {g: regressions(r["supervision"], r[backend]) for g, r in result.items()}
        improved = any(
            score["counts"].get(metric, 0) > result[g]["supervision"]["pairs"][name]["counts"].get(metric, 0)
            for g, r in result.items() for name, score in r[backend]["pairs"].items()
            for metric in ("same_correct", "different_correct"))
        decisions[backend] = dict(regressions=failures, person_improvement=improved,
                                  development_pass=not any(failures.values()) and improved)
    if hashes != {str(p): digest(p) for p in paths}:
        raise ValueError("input or implementation changed during comparison")
    report = dict(manifest=manifest, results=result, decisions=decisions,
                  timing_scope="Single-process tracker update including OSNet crop/preprocess/CUDA inference when appearance enabled; excludes model load, detector, decoding and color fitting; not live FPS",
                  identity_scope="Sparse source-box visual relations; not full-video IDF1/HOTA",
                  production_changed=False)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decisions, indent=2))


if __name__ == "__main__":
    main()
