"""Replay the production perimeter filter on immutable raw observations.

Mapping labels from segment 0 only name anonymous slots. Evaluation labels
cannot influence the filter, colour clustering or palette anchor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.tracking.calibration import PitchCalibration
from app.tracking.person_filter import filter_person_tracks
from app.tracking.pipeline import SampledObservation
from app.tracking.teams import TeamAssigner, distinct_team_colors
from scripts.soccertrack_v2.benchmark_daylight_kits import KITS, daylight_score, no_regression


def evaluate(payloads: dict[int, dict], mapping_rows: list[dict], rows: list[dict]) -> dict:
    results = {}
    for enabled, name in ((False, "baseline"), (True, "perimeter_v1")):
        predictions, retained, assignments, diagnostics, anchor = {}, set(), {}, {}, None
        for segment, data in sorted(payloads.items()):
            samples = [SampledObservation(**s) for s in data["samples"]]
            stats = filter_person_tracks(samples, PitchCalibration.from_dict(data["calibration"]), enabled=enabled)
            eligible = {p[0] for s in samples for p in s.persons}
            retained.update((segment, s.frame_idx, p[0]) for s in samples for p in s.persons)
            assigner = TeamAssigner()
            for track, colors in data["colors"].items():
                for color in colors:
                    assigner.observe(int(track), np.asarray(color))
            assignment = assigner.fit(anchor, eligible_tracks=eligible)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = np.array([[round(float(c), 1) for c in row] for row in assignment.centers])
            predictions.update({(segment, p[0]): assignment.team_by_track.get(p[0]) if p[0] in eligible else None
                                for s in data["samples"] for p in s["persons"]})
            assignments[str(segment)] = assignment.team_by_track
            counts = [[sum(assignment.team_by_track.get(p[0]) == t for p in s.persons) for t in (0, 1)] for s in samples]
            diagnostics[str(segment)] = {**stats, "frames": len(samples),
                "overfull_frames": sum(max(c) > 11 for c in counts),
                "palette": assignment.centers.tolist(), "assignment_note": assignment.note}
        direct = daylight_score(mapping_rows, predictions, 0)
        reverse = daylight_score(mapping_rows, predictions, 1)
        if direct["correct"] == reverse["correct"]:
            raise ValueError("mapping clip must distinguish kit names")
        blue = int(reverse["correct"] > direct["correct"])
        score = daylight_score(rows, predictions, blue)
        remaining = Counter(r["kit"] for r in rows if (r["segment"], r["frame_idx"], r["track"]) in retained)
        score.update(kit_boxes_removed=sum(r["kit"] in ("blue", "white") and
                    (r["segment"], r["frame_idx"], r["track"]) not in retained for r in rows),
                     not_person_remaining=remaining["not_person"], other_remaining=remaining["other"])
        results[name] = {"blue_team_from_mapping": blue, "score": score, "diagnostics": diagnostics,
                         "team_by_track": assignments,
                         "retained_ids": [r["id"] for r in rows if (r["segment"], r["frame_idx"], r["track"]) in retained],
                         "predictions": {r["id"]: predictions[r["segment"], r["track"]] for r in rows}}
    return results


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def filter_digest(path: Path) -> str:
    # Git may check out CRLF on Windows; freeze code content in LF form.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def load_inputs(caches: list[Path], labels: list[Path], mapping: Path) -> tuple[dict, list, list, dict]:
    documents = [json.loads(p.read_text(encoding="utf-8")) for p in labels]
    mapping_doc = json.loads(mapping.read_text(encoding="utf-8"))
    rows = [r for d in documents for r in d["records"]]
    mapping_rows = [r for r in mapping_doc["records"] if r["segment"] == 0]
    if not mapping_rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("unique evaluation rows and mapping segment 0 required")
    if any(r["kit"] not in KITS for r in rows + mapping_rows):
        raise ValueError("complete image labels required")
    payloads, hashes = {}, {}
    for segment in sorted({r["segment"] for r in rows + mapping_rows}):
        paths = [c / f"seg_{segment:04d}.json" for c in caches if (c / f"seg_{segment:04d}.json").exists()]
        if len(paths) != 1:
            raise ValueError(f"need exactly one cache for segment {segment}")
        path = paths[0]
        d = json.loads(path.read_text(encoding="utf-8"))
        if (d["config"].get("normalize_kit_light", False) or d["config"].get("filter_off_pitch_tracks", False)
                or d.get("stats", {}).get("person_filter", {}).get("applied", False)):
            raise ValueError("baseline must retain raw colours and unfiltered tracks")
        samples = {(s["frame_idx"], p[0]): (s, p) for s in d["samples"] for p in s["persons"]}
        for row in rows + mapping_rows:
            if row["segment"] != segment:
                continue
            sample, box = samples[row["frame_idx"], row["track"]]
            if list(box[1:5]) != row["bbox"] or sample["seconds"] != row["seconds"] or row["video"] != d["video"]:
                raise ValueError("labels differ from source boxes")
        # Every box at each annotated frame must remain in the measurement.
        for group in (rows, mapping_rows):
            selected = [r for r in group if r["segment"] == segment]
            frames = {r["frame_idx"] for r in selected}
            if {(r["frame_idx"], r["track"]) for r in selected} != {k for k in samples if k[0] in frames}:
                raise ValueError("all source boxes required at each labelled frame")
        known = {v for doc in documents + [mapping_doc] for k,v in doc["input_sha256"].items()
                 if Path(k).name == path.name}
        if known != {digest(path)}:
            raise ValueError("label/cache hash mismatch")
        video = Path(d["video"])
        known_video = {v for doc in documents + [mapping_doc] for k,v in doc["input_sha256"].items()
                       if Path(k).as_posix() == video.as_posix()}
        if known_video != {digest(video)}:
            raise ValueError("label/video hash mismatch")
        payloads[segment] = d
        hashes[path.as_posix()] = digest(path)
    return payloads, mapping_rows, rows, {"cache_sha256": hashes,
        "label_sha256": {p.as_posix(): digest(p) for p in labels + [mapping]}}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, nargs="+", required=True)
    p.add_argument("--labels", type=Path, nargs="+", required=True)
    p.add_argument("--mapping-labels", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--decision", type=Path)
    p.add_argument("--export", type=Path)
    args = p.parse_args()
    if args.out.exists() or (args.export and args.export.exists()):
        p.error("choose new output paths")
    code_path = Path("app/tracking/person_filter.py")
    if args.decision:
        frozen = json.loads(args.decision.read_text(encoding="utf-8"))
        if frozen["filter_sha256"] != filter_digest(code_path):
            p.error("filter changed after decision was frozen")
    payloads, mapping_rows, rows, provenance = load_inputs(args.cache, args.labels, args.mapping_labels)
    results = evaluate(payloads, mapping_rows, rows)
    before, after = (results[m]["score"] for m in ("baseline", "perimeter_v1"))
    passed = no_regression(before, after) and after["kit_boxes_removed"] == 0
    report = {**provenance, "filter_sha256": filter_digest(code_path), "results": results,
              "no_regression": passed, "fewer_false_boxes": after["not_person_remaining"] < before["not_person_remaining"],
              "decision_sha256": digest(args.decision) if args.decision else None,
              "scope": "Single-reviewer detected-box labels; not player recall or event accuracy. Correlated tracks."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    if args.export:
        args.export.mkdir(parents=True)
        for s, data in payloads.items():
            samples = [SampledObservation(**r) for r in data["samples"]]
            stats = filter_person_tracks(samples, PitchCalibration.from_dict(data["calibration"]))
            exported = {**data, "samples": [asdict(x) for x in samples],
                        "config": {**data["config"], "filter_off_pitch_tracks": True},
                        "stats": {**data["stats"], "person_filter": stats}}
            (args.export / f"seg_{s:04d}.json").write_text(json.dumps(exported)+"\n", encoding="utf-8")
    print(json.dumps({m:r["score"] for m,r in results.items()} | {"no_regression": passed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
