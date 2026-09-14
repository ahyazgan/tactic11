"""One-to-one, two-endpoint SkillCorner regression; provider actors, not video detection.

Unlike validate_passes.py's legacy metric, skipped possessions do not count as
correct passes, recipients must be time-aligned and each reference is used once.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.tracking.passes import extract_passes
from scripts.validate_passes import FPS, _load_frames, _possession_chain


def strict_matches(passes, chain, team_of, tolerance_seconds=3.0):
    references = [(a, b) for a, b in zip(chain, chain[1:], strict=False) if a[2] != b[2]]
    choices = []
    tol = tolerance_seconds * FPS
    for p in passes:
        departure = p.minute * 60 * FPS
        arrival = departure + p.flight_seconds * FPS
        eligible = []
        for j, (a, b) in enumerate(references):
            if (p.from_player_external_id != a[2] or p.to_player_external_id != b[2]
                    or p.complete != (team_of.get(a[2]) == team_of.get(b[2]))):
                continue
            if a[0] - tol <= departure <= a[1] + tol and b[0] - tol <= arrival <= b[1] + tol:
                eligible.append((abs(departure - a[1]) + abs(arrival - b[0]), j))
        choices.append([j for _, j in sorted(eligible)])
    # Maximum bipartite matching: duplicates cannot inflate precision/recall.
    owner = {}
    def assign(i, seen):
        for j in choices[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or assign(owner[j], seen):
                owner[j] = i
                return True
        return False
    for i in range(len(passes)):
        assign(i, set())
    return len(owner), len(references)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-module", type=Path, help="trusted local copy of prior app/tracking/passes.py")
    args = parser.parse_args()
    meta = json.loads((args.dir / "match.json").read_text(encoding="utf-8"))
    team_of = {p["id"]: p["team_id"] for p in meta["players"]}
    frames = _load_frames(args.dir, team_of)
    chain = _possession_chain(args.dir)
    extractors = {"current": extract_passes}
    if args.baseline_module:
        spec = importlib.util.spec_from_file_location("baseline_passes", args.baseline_module)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        extractors["baseline"] = module.extract_passes
    report = {"frames": len(frames), "tolerance_seconds": 3,
              "limitations": "Shared provider possession actors/reference; algorithm regression, not independent video accuracy.",
              "results": {}}
    for name, extract in extractors.items():
        result = extract(frames)
        matches, reference_count = strict_matches(result.passes, chain, team_of)
        report["results"][name] = {"predicted": len(result.passes), "references": reference_count,
                                   "strict_matches": matches, "unmatched": len(result.passes) - matches,
                                   "precision": matches / max(1, len(result.passes)),
                                   "recall": matches / max(1, reference_count),
                                   "rejected": result.rejected,
                                   "passes": [asdict(p) for p in result.passes]}
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: {a: b for a, b in v.items() if a != "passes"}
                      for k, v in report["results"].items()}, indent=2))


if __name__ == "__main__":
    main()
