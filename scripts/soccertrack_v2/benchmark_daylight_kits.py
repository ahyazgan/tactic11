"""External daylight validation of the frozen production kit colour method.

Match 117093: segment 0 maps anonymous team slots to shirt names; 3/6/9 are
control. Missing source clips must be recorded before image labels are read.
No method, detector, threshold or track is selected using control labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, distinct_team_colors
from scripts.soccertrack_v2.benchmark_kit_colors import score
from scripts.soccertrack_v2.prepare_kit_review import select_samples

PLANNED = {0, 3, 6, 9}
KITS = {"blue", "white", "other", "uncertain", "not_person"}


def daylight_score(rows: list[dict], predictions: dict, blue_team: int) -> dict:
    people = [r for r in rows if r["kit"] != "not_person"]
    result = score(people, predictions, blue_team)
    non_people = [r for r in rows if r["kit"] == "not_person"]
    result.update(samples=len(rows), not_person_detections=len(non_people),
                  not_person_assigned=sum(predictions[r["segment"], r["track"]] is not None for r in non_people))
    return result


def no_regression(before: dict, after: dict) -> bool:
    population = ("samples", "labeled_players", "other_people", "uncertain", "not_person_detections")
    return (all(before[k] == after[k] for k in population)
            and after["correct"] >= before["correct"] and after["wrong"] <= before["wrong"]
            and after["other_assigned"] <= before["other_assigned"]
            and after["not_person_assigned"] <= before["not_person_assigned"])


def benchmark(payloads: dict[int, dict], rows: list[dict]) -> dict:
    results = {}
    for method in ("raw_rgb_v1", "local_grass_v1"):
        predictions, tracks, diagnostics, anchor = {}, {}, {}, None
        for segment, payload in sorted(payloads.items()):
            assigner = TeamAssigner()
            colors = payload["colors"] if method == "raw_rgb_v1" else payload["alternative_colors"]["local_grass"]
            for track, observations in colors.items():
                for color in observations:
                    assigner.observe(int(track), np.asarray(color))
            eligible = {p[0] for s in payload["samples"] for p in s["persons"]}
            assignment = assigner.fit(anchor, eligible_tracks=eligible)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = np.array([[round(float(c), 1) for c in row] for row in assignment.centers])
            predictions.update({(segment, t): assignment.team_by_track.get(t) for t in eligible})
            tracks[segment] = assignment.team_by_track
            counts = [[sum(assignment.team_by_track.get(p[0]) == team for p in s["persons"])
                       for team in (0, 1)] for s in payload["samples"]]
            diagnostics[segment] = {
                "sampled_frames": len(counts), "eligible_track_ids": len(eligible),
                "detected_boxes_per_frame_mean": float(np.mean([len(s["persons"]) for s in payload["samples"]])),
                "assigned_boxes_per_frame_mean": float(np.mean([sum(c) for c in counts])),
                "frames_with_more_than_11_in_one_team": sum(max(c) > 11 for c in counts),
                "ball_sources": {source: sum(s.get("ball_source") == source for s in payload["samples"])
                                 for source in ("det", "roi", "interp")},
                "palette": assignment.centers.tolist(), "note": assignment.note,
            }
        mapping_rows = [r for r in rows if r["segment"] == 0]
        direct, reverse = daylight_score(mapping_rows, predictions, 0), daylight_score(mapping_rows, predictions, 1)
        if direct["correct"] == reverse["correct"]:
            raise ValueError("segment 0 cannot establish a unique shirt-name mapping")
        blue_team = int(reverse["correct"] > direct["correct"])
        results[method] = {
            "blue_team_from_segment_0": blue_team,
            "mapping_clip": daylight_score(mapping_rows, predictions, blue_team),
            "control": daylight_score([r for r in rows if r["segment"] != 0], predictions, blue_team),
            "predictions": {r["id"]: predictions[r["segment"], r["track"]] for r in rows},
            "team_by_track": tracks, "diagnostics": diagnostics,
        }
    return results


def load_inputs(cache: Path, labels: Path, source: Path) -> tuple[dict, list[dict], dict]:
    manifest = json.loads(source.read_text(encoding="utf-8"))
    annotation = json.loads(labels.read_text(encoding="utf-8"))
    clips = {r["segment"]: r for r in manifest["clips"]}
    unavailable = {int(s) for s in manifest.get("unavailable_segments", {})}
    if (manifest["match"] != "117093" or len(clips) != len(manifest["clips"])
            or set(clips) | unavailable != PLANNED or set(clips) & unavailable
            or 0 not in clips or len(clips) < 2):
        raise ValueError("need mapping clip 0 and available planned controls, with missing clips declared")
    rows = annotation["records"]
    if (len({r["id"] for r in rows}) != len(rows) or {r["segment"] for r in rows} != set(clips)
            or any(r["kit"] not in KITS for r in rows)):
        raise ValueError("unique, fully labelled observations required for every available clip")
    payloads, hashes = {}, {}
    for segment, clip in sorted(clips.items()):
        path = cache / f"seg_{segment:04d}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        experiment = payload["colour_experiment"]
        if not experiment.get("raw_observations_exactly_reproduced"):
            raise ValueError("raw colour observations must be verified against the source")
        known = {v for k, v in annotation["input_sha256"].items() if Path(k).name == path.name}
        if known != {experiment["source_sha256"]}:
            raise ValueError(f"label/cache mismatch for segment {segment}")
        video = Path(payload["video"])
        if video.resolve() != Path(clip["path"]).resolve() or hashlib.sha256(video.read_bytes()).hexdigest() != clip["sha256"]:
            raise ValueError(f"source video mismatch for segment {segment}")
        selected = {r["id"]: r for r in select_samples(payload, [5.0, 20.0])}
        actual = {r["id"]: r for r in rows if r["segment"] == segment}
        if selected.keys() != actual.keys() or any(
            any(actual[key][field] != value[field] for field in ("segment", "track", "frame_idx", "bbox", "seconds", "video"))
            for key, value in selected.items()
        ):
            raise ValueError(f"labels must retain every fixed-time source box in segment {segment}")
        payloads[segment] = payload
        hashes[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return payloads, rows, {"source": manifest, "cache_sha256": hashes,
                            "label_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
                            "source_manifest_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output path")
    payloads, rows, provenance = load_inputs(args.cache, args.labels, args.source_manifest)
    results = benchmark(payloads, rows)
    before, after = results["raw_rgb_v1"]["control"], results["local_grass_v1"]["control"]
    report = {**provenance, "frozen_production_change": "93d2413", "mapping_segments": [0],
              "available_control_segments": sorted(set(payloads) - {0}),
              "metric_scope": "Direct kit labels on detected boxes; not detection recall, player identity or event accuracy. Single reviewer, correlated frames.",
              "results": results, "control_no_regression": no_regression(before, after),
              "control_strict_gain": no_regression(before, after) and after["correct"] > before["correct"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scores": {m: {k:v for k,v in r.items() if k in ("mapping_clip", "control")}
                                 for m,r in results.items()},
                      "control_no_regression": report["control_no_regression"],
                      "control_strict_gain": report["control_strict_gain"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
