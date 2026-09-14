"""Team assignment benchmark on cached, identical detector observations.

The first two cached segments select ONE time offset and team permutation.
Remaining segments are held out for classification, using that frozen alignment.
Spatial labels are conditional on a one-to-one match within --match-radius metres;
this is not an independent calibration evaluation or overall detector accuracy.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.tracking.calibration import PitchCalibration
from app.tracking.teams import TeamAssigner


def matched(pts, gt, radius):
    if not len(pts) or not len(gt):
        return []
    dist = np.linalg.norm(pts[:, None] - (gt[None, :, 6:8] + [52.5, 34]), axis=-1)
    # Penalise invalid pairs so assignment maximises the number of valid matches.
    cost = np.where(dist <= radius, dist, 1000 + dist)
    ii, jj = linear_sum_assignment(cost)
    return [(int(i), int(j)) for i, j in zip(ii, jj, strict=True) if dist[i, j] <= radius]


def load_samples(cache: Path):
    data = []
    for path in sorted(cache.glob("seg_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cal = PitchCalibration.from_dict(payload["calibration"])
        samples = []
        for s in payload["samples"][::10]:
            pts = np.array([cal.image_to_pitch_m((r[1] + r[3]) / 2, r[4]) for r in s["persons"]]).reshape(-1, 2)
            samples.append((600 + payload["segment"] * 30 + s["seconds"], s["persons"], pts))
        data.append((payload, samples))
    return data


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--alignment", type=Path, required=True)
    p.add_argument("--match-radius", type=float, default=3.0)
    p.add_argument("--baseline", action="store_true", help="include discarded short tracks in clustering (old behaviour)")
    args = p.parse_args()
    data = load_samples(args.cache)
    if len(data) < 4:
        p.error("at least four segments required (two development, two control)")
    rows = np.load(args.gt)
    ids, starts = np.unique(rows[:, 0].astype(int), return_index=True)
    gt = {int(f): a for f, a in zip(ids, np.split(rows, starts[1:]), strict=True)}
    empty = np.empty((0, 10))
    if args.alignment.exists():
        alignment = json.loads(args.alignment.read_text())
    else:
        # Select the offset with best average capped nearest-GT distance on development.
        scores = []
        for delta in range(-250, 251):
            losses = []
            for _, samples in data[:2]:
                for t, _, pts in samples[::3]:
                    g = gt.get(round(t * 25) + 1 + delta, empty)
                    if len(g) and len(pts):
                        distances = np.linalg.norm(pts[:, None] - (g[None, :, 6:8] + [52.5, 34]), axis=-1)
                        losses.extend(np.minimum(distances.min(0), 6))
            scores.append((float(np.mean(losses)) if losses else float("inf"), delta))
        alignment = {"delta_frames": min(scores)[1], "fps": 25, "sample_start_seconds": 600,
                     "development_segments": [d[0]["segment"] for d in data[:2]],
                     "note": "fixed on development; no per-frame search on control"}
        args.alignment.write_text(json.dumps(alignment, indent=2), encoding="utf-8")
    anchor = None
    records = []
    for payload, samples in data:
        assigner = TeamAssigner(reject_color_outliers=not args.baseline)
        for track, colors in payload["colors"].items():
            for color in colors:
                assigner.observe(int(track), np.array(color))
        eligible = {r[0] for s in payload["samples"] for r in s["persons"]}
        assignment = assigner.fit(anchor, eligible_tracks=None if args.baseline else eligible)
        if anchor is None:
            anchor = assignment.centers
        labels = []
        counts = []
        for t, people, pts in samples:
            g = gt.get(round(t * 25) + 1 + alignment["delta_frames"], empty)
            for i, j in matched(pts, g, args.match_radius):
                # Goalkeepers use different shirts and are reported separately.
                if g[j, 3] == 1:
                    labels.append((assignment.team_by_track.get(people[i][0]), int(g[j, 2])))
        for sample in payload["samples"]:
            counts.append(Counter(assignment.team_by_track.get(r[0]) for r in sample["persons"]))
        records.append({"segment": payload["segment"], "labels": labels, "counts": counts})
    dev_labels = [x for r in records[:2] for x in r["labels"]]
    direct = sum(a == b for a, b in dev_labels)
    reverse = sum(a is not None and 1 - a == b for a, b in dev_labels)
    swap = reverse > direct
    report = {"alignment": alignment, "swap_teams_from_development": swap,
              "match_radius_m": args.match_radius, "baseline": args.baseline, "splits": {}}
    for name, group in (("development", records[:2]), ("control", records[2:])):
        labels = [x for r in group for x in r["labels"]]
        assigned = sum(a is not None for a, _ in labels)
        correct = sum(a is not None and (1 - a if swap else a) == b for a, b in labels)
        counts = [x for r in group for x in r["counts"]]
        report["splits"][name] = {
            "segments": [r["segment"] for r in group], "frames": len(counts),
            "matched_outfield_observations": len(labels), "assigned_matched": assigned,
            "correct_matched": correct,
            "accuracy_when_assigned": correct / assigned if assigned else None,
            "correct_fraction_of_matched": correct / len(labels) if labels else None,
            "unassigned_matched": len(labels) - assigned,
            "overfull_frame_ratio": sum(max(c[0], c[1]) > 11 for c in counts) / len(counts),
            "assigned_per_frame": sum(c[0] + c[1] for c in counts) / len(counts),
        }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
