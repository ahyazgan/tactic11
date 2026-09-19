"""Development-only backend comparison on immutable pre-tracker detections.

The production retrack helper owns pitch/short-track filtering and kit evidence.
Only its tracker factory is substituted, within a bounded mock context. No
production defaults, source caches, frozen labels or old reports are edited.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from scripts.soccertrack_v2.benchmark_joint_identity import (
    adjudicated_rows,
    predictions,
    score_pairs,
    source_boxes,
)
from scripts.soccertrack_v2.benchmark_track_buffer import box_key, retrack, score_rows

BACKENDS = ("supervision", "roboflow_byte", "botsort", "ocsort")
MEASUREMENTS = Path("docs/measurements")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def backend_settings(data: dict, backend: str) -> dict:
    if backend not in BACKENDS:
        raise ValueError("unknown tracker backend")
    fps = float(data["stats"]["effective_track_fps"])
    cfg = data["config"]
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("positive effective FPS required")
    legacy_buffer = max(1, int(cfg["lost_track_seconds"] * fps))
    lost_frames = int(max(1, round(fps)) / 30 * legacy_buffer)
    if backend == "supervision":
        return dict(track_activation_threshold=cfg["track_activation_threshold"],
                    lost_track_buffer=legacy_buffer, frame_rate=max(1, round(fps)),
                    minimum_matching_threshold=.8, minimum_consecutive_frames=1)
    # External APIs express buffers in frames at 30 FPS. Supply the actual
    # baseline frame lifetime at frame_rate=30; timestamps are deliberately absent.
    settings = dict(lost_track_buffer=lost_frames, frame_rate=30.,
                    minimum_consecutive_frames=1,
                    high_conf_det_threshold=cfg["track_activation_threshold"])
    if backend != "ocsort":
        threshold = cfg["track_activation_threshold"]
        settings["track_activation_threshold"] = threshold + .1 if threshold <= .9 else threshold
    if backend == "botsort":
        settings["enable_cmc"] = False
    return settings


class EvidenceTracker:
    """Preserve source rows; never turn unconfirmed -1 IDs into one person."""

    def __init__(self, tracker, *, external: bool):
        self.tracker = tracker
        self.external = external
        self.max_time_lost = (tracker.maximum_frames_without_update if external
                              else tracker.max_time_lost)
        self.update_seconds: list[float] = []
        self.unconfirmed = 0

    def update_with_detections(self, detections):
        original = {int(i): (box.copy(), float(conf)) for i, box, conf in zip(
            detections.data["raw_index"], detections.xyxy, detections.confidence, strict=True)}
        start = perf_counter()
        result = (self.tracker.update(detections) if self.external
                  else self.tracker.update_with_detections(detections))
        self.update_seconds.append(perf_counter() - start)
        ids = result.tracker_id
        if ids is None:
            raise ValueError("tracker did not return IDs")
        if self.external:
            self.unconfirmed += int(np.count_nonzero(ids < 0))
            result = result[ids >= 0]
            result.tracker_id = result.tracker_id + 1
        if len(set(map(int, result.tracker_id))) != len(result):
            raise ValueError("duplicate identity in one frame")
        if not len(result):
            # Some libraries return Detections.empty() without custom metadata.
            result.data["raw_index"] = np.array([], dtype=int)
            return result
        indices = result.data.get("raw_index")
        if indices is None or len(set(map(int, indices))) != len(result):
            raise ValueError("missing or repeated source detection index")
        for index, box, conf in zip(indices, result.xyxy, result.confidence, strict=True):
            if int(index) not in original:
                raise ValueError("tracker invented a source detection")
            source_box, source_conf = original[int(index)]
            if not np.array_equal(box, source_box) or conf != source_conf:
                raise ValueError("tracker changed source box or confidence")
        return result


def replay(data: dict, backend: str, anchor: np.ndarray) -> tuple[dict, dict]:
    import supervision as sv

    settings = backend_settings(data, backend)
    if backend == "supervision":
        tracker = sv.ByteTrack(**settings)
    else:
        import trackers

        classes = dict(roboflow_byte=trackers.ByteTrackTracker,
                       botsort=trackers.BoTSORTTracker, ocsort=trackers.OCSORTTracker)
        tracker = classes[backend](**settings)
    wrapped = EvidenceTracker(tracker, external=backend != "supervision")
    with patch.object(sv, "ByteTrack", return_value=wrapped):
        samples, teams, stats = retrack(data, correct_buffer=False)
    if backend == "supervision":
        if [[list(p) for p in s.persons] for s in samples] != [s["persons"] for s in data["samples"]]:
            raise ValueError("baseline person rows differ from source")
        if {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()} != data["colors"]:
            raise ValueError("baseline color histories differ from source")
    assignment = teams.fit(anchor, eligible_tracks={p[0] for s in samples for p in s.persons})
    for sample in samples:
        sample.person_teams = {str(p[0]): assignment.team_by_track.get(p[0]) for p in sample.persons}
    payload = {"samples": [asdict(s) for s in samples]}
    defaults = {k: repr(p.default) for k, p in inspect.signature(type(tracker)).parameters.items()}
    stats.update(settings=settings, constructor_defaults=defaults,
                 baseline_exact=backend == "supervision",
                 tracking_update_ms={"mean": 1000 * float(np.mean(wrapped.update_seconds)),
                                     "p95": 1000 * float(np.percentile(wrapped.update_seconds, 95)),
                                     "frames": len(wrapped.update_seconds)},
                 unconfirmed_observations_excluded=wrapped.unconfirmed,
                 observations=sum(len(s.persons) for s in samples),
                 tracks=len({p[0] for s in samples for p in s.persons}))
    return payload, stats


def pair_subset(labels: dict, excluded: set) -> dict:
    """Exclude annotated body-part endpoints, retaining unknown pair labels."""
    keep = {r["id"] for r in labels["observations"]
            if (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in excluded}
    return {"observations": [r for r in labels["observations"] if r["id"] in keep],
            "pairs": [p for p in labels["pairs"] if p["left"] in keep and p["right"] in keep]}


def regressions(before: dict, after: dict) -> list[str]:
    failed = []
    for metric in ("correct", "wrong", "unassigned", "kit_boxes_missing", "other_assigned"):
        b, a = before["kit"][metric], after["kit"][metric]
        if (a < b if metric == "correct" else a > b):
            failed.append(f"kit.{metric}")
    for name, base in before["pairs"].items():
        candidate = after["pairs"][name]
        for metric in ("same_correct", "different_correct", "false_split", "false_join"):
            b, a = base["counts"].get(metric, 0), candidate["counts"].get(metric, 0)
            if (a < b if metric.endswith("correct") else a > b):
                failed.append(f"{name}.{metric}")
        if candidate["covered_observations"] < base["covered_observations"]:
            failed.append(f"{name}.coverage")
        outcomes = {(r["left"], r["right"]): r for r in candidate["outcomes"]}
        for row in base["outcomes"]:
            if row["passed"] and not outcomes[row["left"], row["right"]]["passed"]:
                failed.append(f"{name}.{row['left']}->{row['right']}")
    return failed


def groups() -> dict:
    return {
        "day": dict(segments=[0, 3, 6], cache="data/tracking/bench/identity_day_detections",
                    labels=["daylight-117093-labels", "perimeter-control-day-labels"],
                    pairs=["identity-person-development-labels", "identity-link-audit-development-labels",
                           "joint-identity-control-day-pairs"],
                    anchor="joint-identity-development-day-results"),
        "night": dict(segments=[0, 3, 6, 9], cache="data/tracking/bench/landmark_candidates_v1",
                      labels=["kit-fixed-development-labels", "kit-fixed-control-labels"], pairs=[],
                      anchor="joint-identity-development-night-results"),
        "night_extra": dict(segments=[20, 30], cache=".cache/kit_joint_agent/night_new_raw_v1",
                            labels=["perimeter-control-night-labels"], pairs=[],
                            anchor="joint-identity-development-night-results"),
        "night_old_control": dict(segments=[40, 50], cache="data/tracking/bench/joint_identity_control/raw_v1",
                                  labels=["joint-identity-control-night-labels"],
                                  pairs=["joint-identity-control-night-pairs"],
                                  anchor="joint-identity-development-night-results"),
    }


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
    paths += list(Path("app/tracking").glob("*.py"))
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
                "versions": {n: version(n) for n in ("trackers", "supervision", "numpy", "scipy")},
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
                payloads[segment], stats[segment] = replay(data, backend, anchor)
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
                  timing_scope="Single-process tracker.update only, no detector, decoding, color fitting or GPU; descriptive, not live FPS",
                  identity_scope="Sparse source-box visual relations; not full-video IDF1/HOTA",
                  production_changed=False)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decisions, indent=2))


if __name__ == "__main__":
    main()
