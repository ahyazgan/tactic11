"""Compare locally normalized kit colour histories; old control is development now."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, distinct_team_colors
from scripts.soccertrack_v2.benchmark_kit_colors import passes_gate, score

DEVELOPMENT = {0, 2, 3, 6, 8, 9}
CONTROL = {1, 7}


def benchmark(payloads: dict, rows: list[dict]) -> dict:
    results = {}
    for method in ("cached", "raw_reextracted", "local_all", "local_grass"):
        predictions, anchor = {}, None
        for segment, payload in sorted(payloads.items()):
            assigner = TeamAssigner()
            colors = payload["colors"] if method == "cached" else payload["alternative_colors"][method]
            for track, observations in colors.items():
                for color in observations:
                    assigner.observe(int(track), np.asarray(color))
            eligible = {p[0] for s in payload["samples"] for p in s["persons"]}
            assignment = assigner.fit(anchor, eligible_tracks=eligible)
            if anchor is None and distinct_team_colors(assignment.centers):
                # WarmTracker receives the process_video summary's 0.1 RGB palette.
                anchor = np.array([[round(float(c), 1) for c in row] for row in assignment.centers])
            predictions.update({(segment, t): assignment.team_by_track.get(t) for t in eligible})
        dev = [r for r in rows if r["segment"] in DEVELOPMENT]
        direct, reverse = score(dev, predictions, 0), score(dev, predictions, 1)
        if direct["correct"] == reverse["correct"]:
            raise ValueError("development cannot establish unique team mapping")
        blue_team = int(reverse["correct"] > direct["correct"])
        result = {"blue_team_from_development": blue_team,
                  "development": score(dev, predictions, blue_team),
                  "predictions": {r["id"]: predictions[r["segment"], r["track"]] for r in rows}}
        control = [r for r in rows if r["segment"] in CONTROL]
        if control:
            result["control"] = score(control, predictions, blue_team)
        results[method] = result
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, nargs="+", required=True)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("choose a new output path")
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in args.labels]
    rows = [r for m in manifests for r in m["records"]]
    if args.development_only:
        rows = [r for r in rows if r["segment"] in DEVELOPMENT]
    expected = DEVELOPMENT if args.development_only else DEVELOPMENT | CONTROL
    if ({r["segment"] for r in rows} != expected or len({r["id"] for r in rows}) != len(rows)
            or any(r["kit"] not in ("blue", "white", "other", "uncertain") for r in rows)):
        parser.error("unique, fully labelled samples required for all expected segments")
    payloads, hashes = {}, {}
    for segment in sorted(expected):
        paths = [p / f"seg_{segment:04d}.json" for p in args.cache if (p / f"seg_{segment:04d}.json").is_file()]
        if len(paths) != 1:
            parser.error(f"exactly one colour cache required for segment {segment}")
        path = paths[0]
        payload = json.loads(path.read_text(encoding="utf-8"))
        for manifest in manifests:
            if any(r["segment"] == segment for r in manifest["records"]):
                original_hashes = {v for k, v in manifest["input_sha256"].items() if Path(k).name == path.name}
                if original_hashes != {payload["colour_experiment"]["source_sha256"]}:
                    parser.error(f"label/source cache mismatch for segment {segment}")
        payloads[segment] = payload
        hashes[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    results = benchmark(payloads, rows)
    if results["cached"]["predictions"] != results["raw_reextracted"]["predictions"]:
        parser.error("raw colour re-extraction changed baseline predictions; comparison is invalid")
    gates = {method: {split: passes_gate(results["cached"][split], results[method][split])
                       for split in ("development", "control") if split in results["cached"]}
             for method in ("local_all", "local_grass")}
    report = {"development_segments": sorted(DEVELOPMENT), "control_segments": sorted(CONTROL),
              "metric_scope": "direct visual labels; same-match clips, one reviewer, correlated frames",
              "anchor_policy": "first distinct palette rounded to 0.1 RGB, as in live summary",
              "cache_sha256": hashes,
              "label_sha256": {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.labels},
              "results": results, "numerical_gate_passed": gates}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scores": {v: {k: x for k, x in r.items() if k in ("development", "control")}
                                  for v, r in results.items()}, "gates": gates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
