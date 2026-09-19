"""Replay immutable detections through the production fixed-camera pipeline.

Only source I/O and pixel feature extraction are substituted. Tracking,
perimeter/part filtering, identity splitting, team fitting and fragment linking
run through the same production functions as recorded video. Kit labels never
enter replay; they only name anonymous team slots and score exact source boxes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.detect import DetectorConfig
from app.tracking.kit_evidence import KitEvidence
from app.tracking.teams import distinct_team_colors
from scripts.soccertrack_v2.benchmark_track_buffer import box_key, score_rows


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def production_hashes() -> dict[str, str]:
    code = [Path(__file__), Path(pipeline.__file__), Path("app/tracking/kit_evidence.py"),
            Path("app/tracking/person_parts.py"), Path("app/tracking/identity_split.py"),
            Path("app/tracking/identity_links.py"), Path("app/tracking/player_identity.py"),
            Path("app/tracking/teams.py"), Path("app/tracking/person_filter.py"),
            Path("app/tracking/identity_namespace.py"), Path("app/tracking/frames.py")]
    return {p.as_posix(): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in code}


def feature_lookup(features: dict) -> dict[tuple, dict]:
    lookup = {}
    for sample in features["samples"]:
        for person in sample["persons"]:
            key = box_key(sample["frame_idx"], person["box"])
            if key in lookup and lookup[key] != person["features"]:
                raise ValueError("Conflicting features for the same source box")
            lookup[key] = person["features"]
    return lookup


def replay(
    data: dict, features: dict, *, refined: bool,
    anchor: np.ndarray | None = None, info: dict | None = None,
) -> dict:
    """Use public detector inputs and production collection; never rebuild ByteTrack."""
    import supervision as sv

    if "detected_persons" not in data:
        raise ValueError("Full pre-tracker detected_persons required; tracked boxes are insufficient")
    if data["config"].get("normalize_kit_light", False):
        raise ValueError("Raw colour observations required")
    if any(s.get("continuity_id", 0) or s.get("calibration") for s in data["samples"]):
        raise ValueError("Fixed-camera continuous source observations required")
    lookup = feature_lookup(features)
    raw_colors = {}
    for sample in data["samples"]:
        for person in data["detected_persons"][str(sample["order"])]:
            key = box_key(sample["frame_idx"], person["box"])
            if key not in lookup:
                raise ValueError(f"Missing raw-detection feature: {key}")
            raw_colors[key] = person["color"]
            if person["color"] is not None and not np.array_equal(
                    lookup[key].get("torso_0.4"), person["color"]):
                raise ValueError(f"Source pixels do not reproduce the cached raw colour: {key}")
    cfg = pipeline.PipelineConfig(**{k: v for k, v in data["config"].items() if k != "detector"},
                                  **({} if "refine_player_identities" in data["config"] else
                                     {"refine_player_identities": refined}))
    cfg.detector = DetectorConfig(**data["config"]["detector"])
    cfg.refine_player_identities = refined
    cal = PitchCalibration.from_dict(data["calibration"])
    video = features.get("video") or data.get("video")
    if not video:
        raise ValueError("Feature cache must identify its source video")
    source_info = dict(info) if info is not None else pipeline.video_info(video)
    state: dict[str, int] = {}

    def frames(*_args, **_kwargs):
        for sample in data["samples"]:
            state["frame"] = sample["frame_idx"]
            state["order"] = sample["order"]
            yield sample["order"], sample["frame_idx"], sample["seconds"], np.zeros((1, 1, 3), np.uint8)

    class CachedDetector:
        def detect(self, _rgb):
            people = data["detected_persons"][str(state["order"])]
            return sv.Detections(xyxy=np.asarray([p["box"] for p in people], dtype=float).reshape(-1, 4),
                                 confidence=np.asarray([p["confidence"] for p in people], dtype=float),
                                 class_id=np.zeros(len(people), dtype=int))

        def split(self, detections):
            return detections, sv.Detections.empty()

    def raw_color(_rgb, box, **_kwargs):
        value = raw_colors[box_key(state["frame"], box)]
        return np.asarray(value, dtype=float) if value is not None else None

    def evidence(_rgb, box):
        values = lookup[box_key(state["frame"], box)]
        if not values:
            return None
        return KitEvidence(*(np.asarray(values[name], dtype=float) for name in
                             ("torso_0.2", "torso_0.4", "torso_bright_saturated")))

    with (patch.object(pipeline, "video_info", return_value=source_info),
          patch.object(pipeline, "iter_video_frames", side_effect=frames),
          patch.object(pipeline, "kit_color", side_effect=raw_color),
          patch.object(pipeline, "extract_kit_evidence", side_effect=evidence)):
        samples, teams, stats = pipeline.collect_observations(
            video, cfg, detector=CachedDetector(), calib=cal, progress=False)
    if not refined:
        if [[list(p) for p in s.persons] for s in samples] != [s["persons"] for s in data["samples"]]:
            raise ValueError("Production baseline does not reproduce source person rows")
        colors = {str(t): [c.tolist() for c in observations] for t, observations in teams._obs.items()}
        if colors != data["colors"]:
            raise ValueError("Production baseline does not reproduce source colour histories")
        assignment = teams.fit(anchor, eligible_tracks={p[0] for s in samples for p in s.persons})
    else:
        from app.tracking.player_identity import refine_player_tracks

        assignment, identity_stats = refine_player_tracks(
            samples, cal, fps_eff=stats["effective_track_fps"], anchor=anchor)
        stats["identity_refinement"] = identity_stats
        stats["kit_color_method"] = "dual_torso_v1"
        grouped: dict[str, list] = defaultdict(list)
        for sample in samples:
            for person in sample.persons:
                value = (sample.person_kit or {}).get(str(person[0]))
                if value is not None:
                    grouped[str(person[0])].append(list(value[3:6]))
        colors = dict(grouped)
    originals = {s["frame_idx"]: s for s in data["samples"]}
    for sample in samples:
        original = originals[sample.frame_idx]
        sample.ball = tuple(original["ball"]) if original.get("ball") is not None else None
        sample.ball_source = original.get("ball_source")
        if sample.person_teams is None:
            sample.person_teams = {str(p[0]): assignment.team_by_track.get(p[0]) for p in sample.persons}
    counts = [[sum(team == slot for team in (sample.person_teams or {}).values()) for slot in (0, 1)]
              for sample in samples]
    stats["player_summary"] = {
        "observations": sum(len(s.persons) for s in samples),
        "tracks": len({p[0] for s in samples for p in s.persons}),
        "unassigned_observations": sum(team is None for s in samples for team in (s.person_teams or {}).values()),
        "overfull_frames": sum(max(count) > 11 for count in counts),
    }
    stats["ball_fields"] = "restored immutable source observations; ball selection was not re-evaluated"
    return {"segment": data["segment"], "video": video, "config": asdict(cfg),
            "calibration": cal.to_dict(), "stats": stats, "colors": colors,
            "samples": [asdict(s) for s in samples],
            "assignment": {"team_by_track": assignment.team_by_track,
                           "centers": assignment.centers.tolist(),
                           "outlier_tracks": sorted(assignment.outlier_tracks), "note": assignment.note},
            "source_video_info": source_info, "baseline_exact": not refined}


def predictions(payloads: dict[int, dict]) -> dict:
    result = {}
    for segment, data in payloads.items():
        for sample in data["samples"]:
            for person in sample["persons"]:
                key = (segment, box_key(sample["frame_idx"], person[1:5]))
                if key in result:
                    raise ValueError("Ambiguous duplicate output box")
                result[key] = (person[0], sample["person_teams"].get(str(person[0])))
    return result


def source_boxes(payloads: dict[int, dict]) -> set[tuple]:
    return {(segment, box_key(s["frame_idx"], p["box"])) for segment, data in payloads.items()
            for s in data["samples"] for p in data["detected_persons"][str(s["order"]) ]}


def score_pairs(labels: dict, payloads: dict[int, dict], available: set[tuple]) -> dict:
    """Only exact source boxes count; new detector misses are separate from refinement."""
    pred = predictions(payloads)
    continuity = {(seg, s["frame_idx"]): s.get("continuity_id", 0)
                  for seg, data in payloads.items() for s in data["samples"]}
    observations, unmatched = {}, []
    for row in labels["observations"]:
        key = (row["segment"], box_key(row["frame_idx"], row["bbox"]))
        if row["id"] in observations:
            raise ValueError("Duplicate pair observation ID")
        if key not in available:
            unmatched.append(row["id"])
        value = pred.get(key)
        observations[row["id"]] = ((row["segment"], continuity[row["segment"], row["frame_idx"]], value[0])
                                   if value is not None else None)
    counts: Counter[str] = Counter()
    outcomes, seen = [], set()
    for pair in labels["pairs"]:
        left, right, relation = pair["left"], pair["right"], pair["relation"]
        if left == right or left not in observations or right not in observations:
            raise ValueError("Invalid identity pair")
        pair_key = tuple(sorted((left, right)))
        if pair_key in seen or relation not in ("same", "different", "uncertain"):
            raise ValueError("Duplicate or invalid identity pair")
        seen.add(pair_key)
        if relation == "uncertain":
            counts["uncertain_excluded"] += 1
            continue
        if left in unmatched or right in unmatched:
            counts["source_unmatched_pairs"] += 1
            continue
        counts[f"{relation}_pairs"] += 1
        a, b = observations[left], observations[right]
        linked = a == b if a is not None and b is not None else None
        passed = linked is not None and linked == (relation == "same")
        counts[f"{relation}_correct"] += int(passed)
        if linked is None:
            counts[f"{relation}_uncovered"] += 1
        elif not passed:
            counts["false_split" if relation == "same" else "false_join"] += 1
        outcomes.append({**pair, "linked": linked, "passed": passed})
    return {"metric_scope": "Sparse visual pairs, not full-video MOT/IDF1",
            "source_unmatched_observations": unmatched, "observations": len(observations),
            "covered_observations": sum(v is not None for v in observations.values()),
            "counts": dict(counts), "outcomes": outcomes}


def score_kits(rows: list, payloads: dict, available: set, *, mapping_segment: int,
               duplicates: set, blue_override: int | None = None) -> dict:
    pred = predictions(payloads)
    matched = [r for r in rows if (r["segment"], box_key(r["frame_idx"], r["bbox"])) in available]
    if blue_override is None:
        mapping = [r for r in matched if r["segment"] == mapping_segment]
        direct, reverse = (score_rows(mapping, pred, blue)["correct"] for blue in (0, 1))
        if direct == reverse:
            raise ValueError("Mapping segment labels must distinguish anonymous team slots")
        blue = int(reverse > direct)
    else:
        if blue_override not in (0, 1):
            raise ValueError("Frozen blue slot must be zero or one")
        blue = blue_override
    unique = [r for r in matched if (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in duplicates]
    return {"blue_slot": blue, "mapping_segment": mapping_segment,
            "slot_source": "development_anchor_report" if blue_override is not None else "mapping_segment_labels",
            "source_matched_labels": len(matched), "source_total_labels": len(rows),
            "source_unmatched_ids": [r["id"] for r in rows if r not in matched],
            "legacy_detected_box_score": score_rows(matched, pred, blue),
            "unique_person_score": score_rows(unique, pred, blue),
            "annotated_duplicate_labels_excluded": len(matched) - len(unique)}


def resolve(patterns: list[str], segment: int) -> Path:
    candidates = []
    for pattern in patterns:
        path = Path(pattern.format(segment=segment, seg=segment))
        if path.is_dir():
            path = path / f"seg_{segment:04d}.json"
        if path.is_file() and path not in candidates:
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"Exactly one source file required for segment {segment}: {candidates}")
    return candidates[0]


def adjudicated_rows(base: list[dict], documents: list[dict]) -> list[dict]:
    """Apply explicitly supplied, source-checked overlays without editing originals."""
    rows = [row for doc in documents for row in doc["records"]]
    if not rows or not any("adjudicated_label" in row for row in rows):
        return rows
    if not all("adjudicated_label" in row for row in rows):
        raise ValueError("Use either complete adjudicated labels or explicit overlays, not a mixture")
    output = deepcopy(base)
    by_id = {row["id"]: row for row in output}
    seen = set()
    for correction in rows:
        identifier = correction["id"]
        if identifier in seen or identifier not in by_id:
            raise ValueError("Overlay must identify one existing original label exactly once")
        seen.add(identifier)
        source = Path(correction["source_labels"])
        if digest(source) != correction["source_labels_sha256"]:
            raise ValueError("Adjudication source label hash mismatch")
        row = by_id[identifier]
        if (row["kit"] != correction["original_label"]
                or any(row[key] != correction[key] for key in ("segment", "frame_idx", "bbox"))):
            raise ValueError("Adjudication overlay disagrees with its original source row")
        row["kit"] = correction["adjudicated_label"]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", nargs="+", required=True, help="Directories or explicit {segment:04d} paths")
    parser.add_argument("--features", nargs="+", required=True, help="Explicit feature directories or {segment:04d} paths")
    parser.add_argument("--segments", nargs="+", type=int, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--kit-labels", nargs="+", type=Path, default=[])
    parser.add_argument("--adjudicated-labels", nargs="+", type=Path, default=[],
                        help="Complete alternative labels or explicit source-checked adjudication overlays")
    parser.add_argument("--pair-labels", nargs="+", type=Path, default=[])
    parser.add_argument("--duplicate-labels", nargs="+", type=Path, default=[])
    parser.add_argument("--mapping-segment", type=int, default=0)
    parser.add_argument("--anchor-report", type=Path,
                        help="Seed both palettes and blue-slot names from a prior development report")
    args = parser.parse_args()
    if args.outdir.exists():
        parser.error("Choose a fresh output directory; preserve previous evidence")
    if len(args.segments) != len(set(args.segments)):
        parser.error("Unique segment numbers required")
    code_hashes = production_hashes()
    inputs, feature_docs, provenance = {}, {}, {}
    anchors: dict[str, np.ndarray | None] = {"before": None, "after": None}
    blue_overrides: dict[str, int | None] = {"before": None, "after": None}
    if args.anchor_report:
        anchor_report = json.loads(args.anchor_report.read_text(encoding="utf-8"))
        provenance[args.anchor_report.as_posix()] = digest(args.anchor_report)
        for name in anchors:
            anchor = np.asarray(anchor_report["anchors"][name], dtype=float)
            if not distinct_team_colors(anchor):
                parser.error("Both frozen development palettes must distinguish two teams")
            anchors[name] = anchor
            slot = anchor_report.get("scores", {}).get(name, {}).get("kit_labels", {}).get("blue_slot")
            if slot not in (0, 1) and (args.kit_labels or args.adjudicated_labels):
                parser.error("Anchor report must supply both development blue-slot names")
            blue_overrides[name] = slot
    for segment in sorted(args.segments):
        cache = resolve(args.cache, segment)
        feature_file = resolve(args.features, segment)
        data, features = (json.loads(p.read_text(encoding="utf-8")) for p in (cache, feature_file))
        if data["segment"] != segment or features["segment"] != segment:
            parser.error("Source segment mismatch")
        if digest(cache) not in features.get("source_sha256", {}).values():
            parser.error("Feature cache does not identify the exact detector source hash")
        video = Path(features["video"])
        if digest(video) not in features.get("source_sha256", {}).values():
            parser.error("Feature cache video hash mismatch")
        inputs[segment], feature_docs[segment] = data, features
        provenance.update({p.as_posix(): digest(p) for p in (cache, feature_file, video)})
    documents = {}
    for group in ("kit_labels", "adjudicated_labels", "pair_labels", "duplicate_labels"):
        documents[group] = [json.loads(path.read_text(encoding="utf-8")) for path in getattr(args, group)]
        provenance.update({path.as_posix(): digest(path) for path in getattr(args, group)})
    kit_rows = [r for doc in documents["kit_labels"] for r in doc["records"]]
    label_groups = {"kit_labels": kit_rows,
                    "adjudicated_labels": adjudicated_rows(kit_rows, documents["adjudicated_labels"])}
    for rows in label_groups.values():
        if (len({r["id"] for r in rows}) != len(rows)
                or any(r["kit"] not in {"blue", "white", "other", "not_person", "uncertain"} for r in rows)):
            parser.error("Unique, complete kit labels required")
    args.outdir.mkdir(parents=True)
    variants: dict[str, dict[int, dict]] = {"before": {}, "after": {}}
    for segment, data in inputs.items():
        for name, refined in (("before", False), ("after", True)):
            payload = replay(data, feature_docs[segment], refined=refined, anchor=anchors[name])
            centers = np.asarray(payload["assignment"]["centers"])
            if anchors[name] is None and distinct_team_colors(centers):
                anchors[name] = np.round(centers, 1)
            variants[name][segment] = payload
            directory = args.outdir / name
            directory.mkdir(exist_ok=True)
            (directory / f"seg_{segment:04d}.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
            print(f"{name} segment {segment}: {sum(len(s['persons']) for s in payload['samples'])} observations", flush=True)
    available = source_boxes(inputs)
    duplicate_rows = [r for doc in documents["duplicate_labels"] for r in doc["records"]
                      if r.get("relation") == "same_person_body_part"]
    duplicate_keys = {(r["segment"], box_key(r["frame_idx"], r["bbox"])) for r in duplicate_rows}
    scores: dict[str, dict[str, Any]] = {}
    for name, payloads in variants.items():
        scores[name] = {}
        for group in ("kit_labels", "adjudicated_labels"):
            rows = label_groups[group]
            if rows:
                if len({r["id"] for r in rows}) != len(rows):
                    raise ValueError("Duplicate kit annotation IDs")
                scores[name][group] = score_kits(rows, payloads, available,
                                                mapping_segment=args.mapping_segment, duplicates=duplicate_keys,
                                                blue_override=blue_overrides[name])
        scores[name]["pair_labels"] = [score_pairs(doc, payloads, available) for doc in documents["pair_labels"]]
        pred = predictions(payloads)
        scores[name]["duplicate_parts"] = {
            "annotated_parts": len(duplicate_rows),
            "source_matched_parts": sum((r["segment"], box_key(r["frame_idx"], r["bbox"])) in available
                                         for r in duplicate_rows),
            "removed_with_support_preserved": sum(
                (r["segment"], box_key(r["frame_idx"], r["bbox"])) in available
                and (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in pred
                and (r["segment"], box_key(r["frame_idx"], r["support_bbox"])) in pred
                for r in duplicate_rows),
        }
    if production_hashes() != code_hashes:
        raise ValueError("Production code changed during replay; choose a fresh run after edits finish")
    report = {"scores": scores, "source_sha256": provenance,
              "production_sha256": code_hashes,
              "anchors": {k: v.tolist() if v is not None else None for k, v in anchors.items()},
              "anchor_report": args.anchor_report.as_posix() if args.anchor_report else None,
              "scope": "Production replay of fixed detections and pixels. No label-driven fitting. Ball fields restored."}
    (args.outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
