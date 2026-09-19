"""Development-only independent motion/color confirmation of identity changes.

An appearance boundary is accepted only when the separate baseline tracker also
changes identity across stable observations. Neither tracker is ground truth.
No boxes are removed and no labels enter the identity/color transformation.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np

from app.tracking.identity_split import appearance_phases
from app.tracking.teams import TeamAssigner
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    MEASUREMENTS,
    adjudicated_rows,
    box_key,
    digest,
    groups,
    load,
    pair_subset,
    predictions,
    regressions,
    score_pairs,
    score_rows,
    source_boxes,
)


def transform(raw: dict, candidate: dict, baseline: dict, anchor: np.ndarray, *, preserve_teams: bool = False) -> tuple[dict, dict]:
    """Retain every candidate observation; split only jointly supported changes."""
    source = {(s["frame_idx"], tuple(r["box"])): r["color"] for s in raw["samples"]
              for r in raw["detected_persons"][str(s["order"]) ]}
    base_ids = {(s["frame_idx"], tuple(p[1:5])): p[0] for s in baseline["samples"] for p in s["persons"]}
    output = deepcopy(candidate)
    tracks = defaultdict(list)
    local_teams = {s["order"]: {} for s in output["samples"]}
    for sample in output["samples"]:
        for index, person in enumerate(sample["persons"]):
            key = (sample["frame_idx"], tuple(person[1:5]))
            if key not in source:
                raise ValueError("Candidate invented a detection")
            tracks[person[0]].append((sample, index, source[key], base_ids.get(key)))
    next_id = max(tracks, default=0) + 1
    audit = []
    assigner = TeamAssigner()
    for original_id, observations in tracks.items():
        colors = [np.asarray(row[2]) if row[2] is not None else None for row in observations]
        _, boundaries = appearance_phases(colors, seconds=[r[0]["seconds"] for r in observations],
            max_gap_seconds=1.5 / raw["stats"]["effective_track_fps"])
        accepted = {}
        for boundary in boundaries:
            start, end = boundary.first_index, boundary.confirmed_index
            before = [r[3] for r in observations[max(0, start - 3):start]]
            after = [r[3] for r in observations[start:end + 1]]
            if (len(before) == 3 and len(after) >= 3 and None not in before + after
                    and len(set(before)) == len(set(after)) == 1 and before[0] != after[0]):
                accepted[start] = next_id
                audit.append(dict(raw_id=original_id, new_id=next_id,
                    first_order=observations[start][0]["order"], confirmed_order=observations[end][0]["order"],
                    prior_motion_id=before[0], new_motion_id=after[0]))
                next_id += 1
        identity = original_id
        for position, (sample, index, _, _) in enumerate(observations):
            identity = accepted.get(position, identity)
            local_teams[sample["order"]][str(identity)] = sample["person_teams"].get(str(original_id))
            sample["persons"][index][0] = identity
            assigner.observe(identity, colors[position])
    assignment = assigner.fit(anchor, eligible_tracks={p[0] for s in output["samples"] for p in s["persons"]})
    for sample in output["samples"]:
        sample["person_teams"] = (local_teams[sample["order"]] if preserve_teams else
                                  {str(p[0]): assignment.team_by_track.get(p[0]) for p in sample["persons"]})
    return output, dict(boundaries=audit, boxes_removed=0, boxes_created=0,
                       observation_teams_preserved=preserve_teams,
                       scope="Causal evidence with retrospective confirmation within the segment; no roster identity")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Completed association comparison directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--direction", choices=["refine_candidate", "refine_baseline"], default="refine_candidate")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output required")
    configs = groups()
    all_paths = [args.input / "report.json", Path(__file__), Path("app/tracking/identity_split.py"), Path("app/tracking/teams.py")]
    all_paths += [MEASUREMENTS / f"{n}.json" for n in ("identity-kit-label-adjudication", "duplicate-part-development-labels", "joint-identity-control-day-labels")]
    for group, cfg in configs.items():
        all_paths += [Path(cfg["cache"]) / f"seg_{s:04d}.json" for s in cfg["segments"]]
        all_paths += [MEASUREMENTS / f"{n}.json" for n in cfg["labels"] + cfg["pairs"] + [cfg["anchor"]]]
        all_paths += [args.input / group / backend / f"seg_{s:04d}.json" for backend in
                      ("supervision", "deepocsort_motion", "deepocsort") for s in cfg["segments"]]
    hashes = {str(p): digest(p) for p in all_paths}
    prior = load(args.input / "report.json")
    args.out.mkdir(parents=True)
    results = {}
    for group, cfg in configs.items():
        inputs = {s: load(Path(cfg["cache"]) / f"seg_{s:04d}.json") for s in cfg["segments"]}
        paths = [Path(cfg["cache"]) / f"seg_{s:04d}.json" for s in cfg["segments"]]
        paths += [MEASUREMENTS / f"{n}.json" for n in cfg["labels"] + cfg["pairs"] + [cfg["anchor"]]]
        anchor = np.asarray(load(MEASUREMENTS / f"{cfg['anchor']}.json")["anchors"]["before"])
        rows = [r for n in cfg["labels"] for r in load(MEASUREMENTS / f"{n}.json")["records"]]
        excluded = set()
        if group == "day":
            paths += [MEASUREMENTS / f"{n}.json" for n in (
                "identity-kit-label-adjudication", "duplicate-part-development-labels",
                "joint-identity-control-day-labels")]
            rows = adjudicated_rows(rows, [load(MEASUREMENTS / "identity-kit-label-adjudication.json")])
            parts = load(MEASUREMENTS / "duplicate-part-development-labels.json")["records"]
            parts += [r for r in load(MEASUREMENTS / "joint-identity-control-day-pairs.json")["observations"] if r.get("duplicate_part_of")]
            excluded = {(r["segment"], box_key(r["frame_idx"], r["bbox"])) for r in parts}
            rows += load(MEASUREMENTS / "joint-identity-control-day-labels.json")["records"]
            rows = [r for r in rows if (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in excluded]
        results[group] = {"supervision": prior["results"][group]["supervision"]}
        for backend in ("deepocsort_motion", "deepocsort"):
            payloads, stats = {}, {}
            for segment, raw in inputs.items():
                candidates = args.input / group / backend / f"seg_{segment:04d}.json"
                base = args.input / group / "supervision" / candidates.name
                paths += [candidates, base]
                candidate_data, base_data = load(candidates), load(base)
                if args.direction == "refine_baseline":
                    payloads[segment], stats[segment] = transform(raw, base_data, candidate_data, anchor, preserve_teams=True)
                else:
                    payloads[segment], stats[segment] = transform(raw, candidate_data, base_data, anchor)
                out = args.out / group / backend / candidates.name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(payloads[segment]) + "\n", encoding="utf-8")
            results[group][backend] = dict(kit=score_rows(rows, predictions(payloads), 0),
                pairs={n: score_pairs(pair_subset(load(MEASUREMENTS / f"{n}.json"), excluded),
                    payloads, source_boxes(inputs)) for n in cfg["pairs"]}, segments=stats)
            print(group, backend, results[group][backend]["kit"], flush=True)
    decisions = {}
    for backend in ("deepocsort_motion", "deepocsort"):
        failures = {g: regressions(r["supervision"], r[backend]) for g, r in results.items()}
        for group, result in results.items():
            if result[backend]["kit"]["conflicting_track_labels"] > result["supervision"]["kit"]["conflicting_track_labels"]:
                failures[group].append("kit.conflicting_track_labels")
        improved = any(score["counts"].get(metric, 0) > result["supervision"]["pairs"][name]["counts"].get(metric, 0)
                       for result in results.values() for name, score in result[backend]["pairs"].items()
                       for metric in ("same_correct", "different_correct"))
        decisions[backend] = dict(regressions=failures, no_regression=not any(failures.values()),
                                 person_improvement=improved, development_pass=not any(failures.values()) and improved)
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Inputs changed during experiment")
    (args.out / "report.json").write_text(json.dumps(dict(scope=__doc__, direction=args.direction, results=results,
        decisions=decisions, hashes=hashes, production_changed=False, new_control_opened=False), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decisions, indent=2))


if __name__ == "__main__":
    main()
