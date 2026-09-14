"""Compare temporal colour summaries on direct image labels, without positional GT.

The bright-quarter experiment stays in scripts until it passes development and
frozen control. Labels are never passed to TeamAssigner; only the two team names
are mapped on development and then frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, distinct_team_colors


def color_observations(colors: np.ndarray, variant: str) -> np.ndarray:
    if variant == "median":
        return colors
    if variant != "bright_quarter":
        raise ValueError(f"unknown variant {variant}")
    count = max(2, math.ceil(len(colors) / 4))
    return colors[np.argsort(colors.max(axis=1), kind="stable")[-count:]] if len(colors) else colors


def score(rows: list[dict], predictions: dict, blue_team: int) -> dict:
    counts = {"samples": len(rows), "labeled_players": 0, "correct": 0, "wrong": 0,
              "unassigned_players": 0, "other_people": 0, "other_assigned": 0, "uncertain": 0}
    for row in rows:
        pred = predictions[row["segment"], row["track"]]
        if row["kit"] == "uncertain":
            counts["uncertain"] += 1
        elif row["kit"] == "other":
            counts["other_people"] += 1
            counts["other_assigned"] += pred is not None
        else:
            counts["labeled_players"] += 1
            expected = blue_team if row["kit"] == "blue" else 1 - blue_team
            counts["unassigned_players" if pred is None else "correct" if pred == expected else "wrong"] += 1
    return counts


def passes_gate(before: dict, after: dict) -> bool:
    """Require more correct observations without hiding losses as abstentions."""
    return (all(before[k] == after[k] for k in ("samples", "labeled_players", "other_people", "uncertain"))
            and after["correct"] > before["correct"]
            and after["wrong"] <= before["wrong"]
            and after["other_assigned"] <= before["other_assigned"])


def benchmark(cache: Path, rows: list[dict]) -> dict:
    results = {}
    for variant in ("median", "bright_quarter"):
        predictions, anchor = {}, None
        for segment in sorted({r["segment"] for r in rows}):
            payload = json.loads((cache / f"seg_{segment:04d}.json").read_text(encoding="utf-8"))
            assigner = TeamAssigner()
            for track, colors in payload["colors"].items():
                for color in color_observations(np.asarray(colors), variant):
                    assigner.observe(int(track), color)
            eligible = {p[0] for s in payload["samples"] for p in s["persons"]}
            assignment = assigner.fit(anchor, eligible_tracks=eligible)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = assignment.centers
            predictions.update({(segment, t): assignment.team_by_track.get(t) for t in eligible})
        dev = [r for r in rows if r["segment"] in (0, 3)]
        direct, reverse = score(dev, predictions, 0), score(dev, predictions, 1)
        if direct["correct"] == reverse["correct"]:
            raise ValueError("development cannot establish a unique team permutation")
        blue_team = int(reverse["correct"] > direct["correct"])
        result = {"blue_team_from_development": blue_team, "development": score(dev, predictions, blue_team)}
        control = [r for r in rows if r["segment"] in (6, 9)]
        if control:
            result["control"] = score(control, predictions, blue_team)
        result["predictions"] = {r["id"]: predictions[r["segment"], r["track"]] for r in rows}
        results[variant] = result
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output path")
    rows = [r for path in args.labels for r in json.loads(path.read_text(encoding="utf-8"))["records"]]
    if args.development_only:
        rows = [r for r in rows if r["segment"] in (0, 3)]
    if (any(r["kit"] not in ("blue", "white", "other", "uncertain") for r in rows)
            or len({r["id"] for r in rows}) != len(rows)
            or any(r["segment"] not in (0, 3, 6, 9) for r in rows)
            or not {0, 3} <= {r["segment"] for r in rows}):
        parser.error("unique, fully labelled development samples are required; supported segments: 0,3,6,9")
    results = benchmark(args.cache, rows)
    report = {"metric_scope": "direct visual shirt labels; single match, single reviewer, correlated frames",
              "label_sha256": {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.labels},
              "cache_sha256": {f"seg_{s:04d}.json": hashlib.sha256((args.cache / f"seg_{s:04d}.json").read_bytes()).hexdigest()
                               for s in sorted({r["segment"] for r in rows})},
              "results": results}
    report["numerical_gate_passed"] = {
        split: passes_gate(results["median"][split], results["bright_quarter"][split])
        for split in ("development", "control") if split in results["median"]
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({v: {k: x for k, x in result.items() if k != "predictions"} for v, result in results.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
