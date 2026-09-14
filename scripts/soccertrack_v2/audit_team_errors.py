"""Audit conditional team mismatches without treating spatial matches as true IDs.

Uses the existing frozen alignment and one-to-one matcher. Diagnostic flags can
overlap: changing matched GT identities may reflect calibration/matching errors,
not necessarily tracker switches. No classifier is fitted using GT labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, distinct_team_colors
from scripts.soccertrack_v2.evaluate_teams import load_samples, matched


def summarize(records: list[dict]) -> dict:
    """Count overlapping warning flags and keep track IDs local to segments."""
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in records:
        groups[row["segment"], row["track"]].append(row)
    assigned = [r for r in records if r["predicted_team"] is not None]
    wrong = [r for r in assigned if r["predicted_team"] != r["gt_team"]]
    multi_team = {key for key, rows in groups.items() if len({r["gt_team"] for r in rows}) > 1}
    multi_id = {key for key, rows in groups.items() if len({r["gt_track"] for r in rows}) > 1}
    ranking = []
    for (segment, track), rows in groups.items():
        errors = [r for r in rows if r["predicted_team"] is not None and r["predicted_team"] != r["gt_team"]]
        if not errors:
            continue
        ranking.append({
            "segment": segment, "track": track, "matched": len(rows), "wrong": len(errors),
            "gt_teams": dict(Counter(r["gt_team"] for r in rows)),
            "gt_tracks": dict(Counter(r["gt_track"] for r in rows)),
            "representative_error": errors[len(errors) // 2],
        })
    ranking.sort(key=lambda r: (-r["wrong"], r["segment"], r["track"]))
    return {
        "matched": len(records), "assigned": len(assigned), "correct": len(assigned) - len(wrong),
        "wrong": len(wrong), "unassigned": len(records) - len(assigned),
        "wrong_with_opposite_gt_in_radius": sum(r["opposite_gt_in_radius"] for r in wrong),
        "wrong_on_track_with_multiple_gt_teams": sum((r["segment"], r["track"]) in multi_team for r in wrong),
        "wrong_on_track_with_multiple_gt_ids": sum((r["segment"], r["track"]) in multi_id for r in wrong),
        "wrong_not_nearest_gt": sum(not r["nearest_gt"] for r in wrong),
        "wrong_within_1_5m": sum(r["distance_m"] <= 1.5 for r in wrong),
        "warning": "Flags overlap and are not causal labels or confirmed tracker switches.",
        "ranked_error_tracks": ranking,
    }


def collect_records(data, gt: dict, alignment: dict, radius: float) -> list[dict]:
    anchor = None
    records = []
    for payload, samples in data:
        assigner = TeamAssigner()
        colors = {int(t): np.asarray(cs) for t, cs in payload["colors"].items()}
        for track, observations in colors.items():
            for color in observations:
                assigner.observe(track, color)
        eligible = {r[0] for s in payload["samples"] for r in s["persons"]}
        assignment = assigner.fit(anchor, eligible_tracks=eligible)
        if anchor is None and distinct_team_colors(assignment.centers):
            anchor = assignment.centers
        for seconds, people, pts in samples:
            frame = round(seconds * alignment["fps"]) + 1 + alignment["delta_frames"]
            labels = gt.get(frame, np.empty((0, 10)))
            for i, j in matched(pts, labels, radius):
                target = labels[j]
                if target[3] != 1 or target[2] not in (0, 1):
                    continue
                distances = np.linalg.norm(pts[i] - (labels[:, 6:8] + [52.5, 34]), axis=1)
                opposite = (labels[:, 3] == 1) & (labels[:, 2] == 1 - target[2])
                opposite_distance = float(distances[opposite].min()) if opposite.any() else None
                track = int(people[i][0])
                observations = colors.get(track)
                median = np.median(observations, axis=0) if observations is not None and len(observations) else None
                records.append({
                    "segment": payload["segment"], "seconds": seconds,
                    "video_seconds": seconds - (600 + payload["segment"] * 30),
                    "video": payload["video"], "track": track,
                    "bbox": people[i][1:5], "predicted_team": assignment.team_by_track.get(track),
                    "gt_frame": frame, "gt_track": int(target[1]), "gt_team": int(target[2]),
                    "distance_m": float(distances[j]),
                    "opposite_gt_distance_m": opposite_distance,
                    "opposite_gt_in_radius": opposite_distance is not None and opposite_distance <= radius,
                    "nearest_gt": bool(distances[j] <= distances.min() + 1e-9),
                    "median_rgb": median.tolist() if median is not None else None,
                    "team_centers_rgb": assignment.centers.tolist(),
                })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--alignment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument("--match-radius", type=float, default=3.0)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output path to preserve evidence")
    if not np.isfinite(args.match_radius) or args.match_radius <= 0:
        parser.error("match radius must be finite and positive")
    alignment = json.loads(args.alignment.read_text(encoding="utf-8"))
    # The shared cache loader currently assumes these source timing values.
    if alignment["sample_start_seconds"] != 600 or alignment["fps"] != 25:
        parser.error("this cache audit requires start=600 seconds and GT fps=25")
    data = load_samples(args.cache)
    if len(data) < 4 or [p["segment"] for p, _ in data[:2]] != alignment["development_segments"]:
        parser.error("cache must contain two frozen development segments followed by control")
    if args.development_only:
        data = data[:2]
    rows = np.load(args.gt)
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    gt = dict(zip(ids, np.split(rows, starts[1:]), strict=True))
    records = collect_records(data, gt, alignment, args.match_radius)
    dev_segments = set(alignment["development_segments"])
    dev = [r for r in records if r["segment"] in dev_segments]
    assigned_dev = [r for r in dev if r["predicted_team"] is not None]
    direct = sum(r["predicted_team"] == r["gt_team"] for r in assigned_dev)
    if not assigned_dev or direct * 2 == len(assigned_dev):
        parser.error("development cannot establish a unique team permutation")
    swap = direct * 2 < len(assigned_dev)
    if swap:
        for row in records:
            if row["predicted_team"] is not None:
                row["predicted_team"] = 1 - row["predicted_team"]
            row["team_centers_rgb"].reverse()
    paths = [args.gt, args.alignment] + [args.cache / f"seg_{p['segment']:04d}.json" for p, _ in data]
    splits = {"development": summarize(dev)}
    if not args.development_only:
        splits["control"] = summarize([r for r in records if r["segment"] not in dev_segments])
    report = {
        "alignment": alignment, "swap_teams_from_development": swap, "match_radius_m": args.match_radius,
        "metric_scope": "agreement with spatially matched GT teams; not verified shirt or player identity accuracy",
        "input_sha256": {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "splits": splits, "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {k: v for k, v in split.items() if k != "ranked_error_tracks"}
                      for name, split in splits.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
