"""Compare tracker lifetimes on identical detector boxes, matching labels by box.

Track IDs are outputs and must never be used to match labels across tracker runs.
This experiment does not change the production configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.person_filter import filter_person_tracks
from app.tracking.pipeline import PipelineConfig, SampledObservation, person_filter_enabled
from app.tracking.teams import TeamAssigner, distinct_team_colors
from scripts.soccertrack_v2.benchmark_daylight_kits import KITS


def box_key(frame: int, box) -> tuple:
    return (frame, *map(float, box))


def retrack(data: dict, *, correct_buffer: bool) -> tuple[list, TeamAssigner, dict]:
    import supervision as sv

    cfg = PipelineConfig(**{k: v for k, v in data["config"].items() if k != "detector"})
    fps = data["stats"]["effective_track_fps"]
    cal = PitchCalibration.from_dict(data["calibration"])
    tracker = sv.ByteTrack(
        track_activation_threshold=cfg.track_activation_threshold,
        lost_track_buffer=(max(1, round(cfg.lost_track_seconds * fps)) if correct_buffer
                           else max(1, int(cfg.lost_track_seconds * fps))),
        frame_rate=30 if correct_buffer else max(1, round(fps)),
        minimum_matching_threshold=.8, minimum_consecutive_frames=1,
    )
    teams, hits, samples = TeamAssigner(), Counter(), []
    for sample in data["samples"]:
        if sample.get("continuity_id", 0) or sample.get("calibration"):
            raise ValueError("fixed-camera observations required")
        raw = data["detected_persons"][str(sample["order"])]
        eligible = [(i, r) for i, r in enumerate(raw) if cal.is_on_pitch(
            (r["box"][0] + r["box"][2]) / 2, r["box"][3], margin_m=cfg.pitch_margin_m)]
        det = sv.Detections(
            xyxy=np.array([r["box"] for _, r in eligible]).reshape(-1, 4),
            confidence=np.array([r["confidence"] for _, r in eligible]),
            class_id=np.zeros(len(eligible), dtype=int),
            data={"raw_index": np.array([i for i, _ in eligible], dtype=int)},
        )
        tracked = tracker.update_with_detections(det)
        people = []
        for box, confidence, tid, index in zip(tracked.xyxy, tracked.confidence,
                tracked.tracker_id, tracked.data["raw_index"], strict=True):
            tid = int(tid)
            people.append((tid, *map(float, box), float(confidence)))
            hits[tid] += 1
            color = raw[int(index)]["color"]
            teams.observe(tid, np.asarray(color) if color is not None else None)
        samples.append(SampledObservation(sample["order"], sample["frame_idx"],
                                         sample["seconds"], people, None))
    for sample in samples:
        sample.persons = [p for p in sample.persons if hits[p[0]] >= max(1, round(cfg.min_track_seconds * fps))]
    filtered = filter_person_tracks(samples, cal, enabled=person_filter_enabled(cfg, cal))
    return samples, teams, {"lost_frames": tracker.max_time_lost,
        "lost_seconds": tracker.max_time_lost / fps, "person_filter": filtered}


def score_rows(rows: list[dict], predictions: dict, blue: int) -> dict:
    score = dict(correct=0, wrong=0, unassigned=0, kit_boxes_missing=0, other_assigned=0,
                 not_person_remaining=0)
    identities = defaultdict(set)
    for row in rows:
        key = (row["segment"], box_key(row["frame_idx"], row["bbox"]))
        present = key in predictions
        tid, team = predictions.get(key, (None, None))
        kit = row["kit"]
        if kit in ("blue", "white"):
            score["kit_boxes_missing"] += not present
            expected = blue if kit == "blue" else 1 - blue
            score["unassigned" if team is None else "correct" if team == expected else "wrong"] += 1
            if present:
                identities[row["segment"], tid].add(kit)
        elif kit == "other":
            score["other_assigned"] += team is not None
        elif kit == "not_person":
            score["not_person_remaining"] += present
    score["conflicting_track_labels"] = sum(len(kits) > 1 for kits in identities.values())
    return score


def evaluate(payloads: dict, rows: list[dict]) -> dict:
    results = {}
    mapping = [r for r in rows if r["segment"] == 0]
    if not mapping:
        raise ValueError("mapping segment 0 required")
    for corrected, name in ((False, "baseline"), (True, "seconds_once")):
        predictions, stats, anchor = {}, {}, None
        for segment, data in sorted(payloads.items()):
            samples, teams, stat = retrack(data, correct_buffer=corrected)
            if not corrected:
                actual = [[list(p) for p in s.persons] for s in samples]
                if actual != [s["persons"] for s in data["samples"]]:
                    raise ValueError(f"baseline does not reproduce source tracks: {segment}")
                colors = {str(t): [c.tolist() for c in cs] for t, cs in teams._obs.items()}
                if colors != data["colors"]:
                    raise ValueError(f"baseline does not reproduce source colours: {segment}")
            tracks = {p[0] for s in samples for p in s.persons}
            assignment = teams.fit(anchor, eligible_tracks=tracks)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = np.round(assignment.centers, 1)
            for sample in samples:
                for person in sample.persons:
                    key = (segment, box_key(sample.frame_idx, person[1:5]))
                    if key in predictions:
                        raise ValueError("ambiguous duplicate box")
                    predictions[key] = (person[0], assignment.team_by_track.get(person[0]))
            stat.update(tracks=len(tracks), observations=sum(len(s.persons) for s in samples),
                        palette=assignment.centers.tolist())
            stats[str(segment)] = stat
        direct, reverse = (score_rows(mapping, predictions, blue)["correct"] for blue in (0, 1))
        if direct == reverse:
            raise ValueError("mapping cannot distinguish teams")
        blue = int(reverse > direct)
        results[name] = {"score": score_rows(rows, predictions, blue), "blue_slot": blue,
                         "per_segment_scores": {str(s): score_rows(
                             [r for r in rows if r["segment"] == s], predictions, blue) for s in payloads},
                         "segments": stats}
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a fresh output file")
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in args.labels]
    rows = [r for d in docs for r in d["records"]]
    if len({r["id"] for r in rows}) != len(rows):
        parser.error("duplicate label rows")
    if any(r["kit"] not in KITS for r in rows):
        parser.error("complete visual labels required")
    paths = [args.cache / f"seg_{s:04d}.json" for s in sorted({r["segment"] for r in rows})]
    payloads = {int(p.stem.split("_")[-1]): json.loads(p.read_text()) for p in paths}
    for r in rows:
        d = payloads[r["segment"]]
        raw = next(s for s in d["samples"] if s["frame_idx"] == r["frame_idx"])
        if raw["seconds"] != r["seconds"] or not any(
                list(p["box"]) == r["bbox"] for p in d["detected_persons"][str(raw["order"]) ]):
            parser.error("label not found in immutable source detections")
    results = evaluate(payloads, rows)
    before, after = (results[k]["score"] for k in ("baseline", "seconds_once"))
    regressions = [k for k in before if (after[k] < before[k] if k == "correct" else after[k] > before[k])]
    report = {"results": results, "input_sha256": {
        p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths + args.labels},
        "experiment_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
        "regressions": regressions, "no_regression": not regressions,
        "scope": "Development only. Same detector boxes; kit conflicts are not complete ID-switch ground truth."}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v["score"] for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
