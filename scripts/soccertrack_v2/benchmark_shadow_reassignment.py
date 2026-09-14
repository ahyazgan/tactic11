"""Compare median and conservative shadow refinement on explicit dev/control clips.

Unlike the earlier benchmark, segments 6/9 are now development. New control
segments 2/8 must not be used to choose the refinement rule or colour mapping.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.tracking.teams import TeamAssigner, TeamAssignment, distinct_team_colors
from scripts.soccertrack_v2.benchmark_kit_colors import passes_gate, score


class ShadowReassignmentAssigner(TeamAssigner):
    """Rejected experiment: keep reproducible here, outside the production path."""

    shadow_reassigned_tracks: frozenset[int] = frozenset()

    def fit(self, anchor_colors=None, *, eligible_tracks=None) -> TeamAssignment:
        base = super().fit(anchor_colors, eligible_tracks=eligible_tracks)
        self.shadow_reassigned_tracks = frozenset()
        if not distinct_team_colors(base.centers):
            return base
        brighter = TeamAssigner(outlier_factor=self._outlier_factor, min_observations=self._min_obs,
                                reject_color_outliers=self._reject_color_outliers)
        for track, observations in self._obs.items():
            if eligible_tracks is not None and track not in eligible_tracks:
                continue
            if len(observations) < self._min_obs:
                continue
            colors = np.asarray(observations)
            count = max(self._min_obs, (len(colors) + 3) // 4)
            order = np.argsort(colors.max(axis=1), kind="stable")[-count:]
            for i in order:
                brighter.observe(track, colors[i])
        bright = brighter.fit(base.centers, eligible_tracks=eligible_tracks)
        corrected = base.team_by_track.copy()
        changes = set()
        for track, team in base.team_by_track.items():
            alternative = bright.team_by_track.get(track)
            if team is not None and alternative is not None and alternative != team:
                corrected[track] = alternative
                changes.add(track)
        self.shadow_reassigned_tracks = frozenset(changes)
        return replace(base, team_by_track=corrected)


def benchmark(payloads: dict, rows: list[dict], development_segments: set[int]) -> dict:
    results = {}
    for refine in (False, True):
        predictions, anchor, changed = {}, None, {}
        for segment, payload in sorted(payloads.items()):
            assigner = ShadowReassignmentAssigner() if refine else TeamAssigner()
            for track, colors in payload["colors"].items():
                for color in colors:
                    assigner.observe(int(track), np.asarray(color))
            eligible = {p[0] for s in payload["samples"] for p in s["persons"]}
            assignment = assigner.fit(anchor, eligible_tracks=eligible)
            if anchor is None and distinct_team_colors(assignment.centers):
                anchor = assignment.centers
            predictions.update({(segment, t): assignment.team_by_track.get(t) for t in eligible})
            changed[segment] = sorted(assigner.shadow_reassigned_tracks) if refine else []
        dev = [r for r in rows if r["segment"] in development_segments]
        direct, reverse = score(dev, predictions, 0), score(dev, predictions, 1)
        if direct["correct"] == reverse["correct"]:
            raise ValueError("development cannot establish a unique team permutation")
        blue_team = int(reverse["correct"] > direct["correct"])
        result = {"blue_team_from_development": blue_team,
                  "development": score(dev, predictions, blue_team),
                  "reassigned_tracks": changed,
                  "predictions": {r["id"]: predictions[r["segment"], r["track"]] for r in rows}}
        control = [r for r in rows if r["segment"] not in development_segments]
        if control:
            result["control"] = score(control, predictions, blue_team)
        results["refined" if refine else "baseline"] = result
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
    dev_segments, control_segments = {0, 3, 6, 9}, {2, 8}
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in args.labels]
    rows = [r for manifest in manifests for r in manifest["records"]]
    if args.development_only:
        rows = [r for r in rows if r["segment"] in dev_segments]
    segments = {r["segment"] for r in rows}
    expected = dev_segments if args.development_only else dev_segments | control_segments
    if (segments != expected or len({r["id"] for r in rows}) != len(rows)
            or any(r["kit"] not in ("blue", "white", "other", "uncertain") for r in rows)):
        parser.error("need unique, fully labelled samples from all expected dev/control segments")
    payloads, hashes = {}, {}
    for segment in sorted(segments):
        matches = [root / f"seg_{segment:04d}.json" for root in args.cache
                   if (root / f"seg_{segment:04d}.json").is_file()]
        if len(matches) != 1:
            parser.error(f"exactly one cache required for segment {segment}")
        path = matches[0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # Reject stale labels: their source boxes came from this exact cache.
        for manifest in manifests:
            if any(r["segment"] == segment for r in manifest["records"]):
                expected_hashes = {v for k, v in manifest["input_sha256"].items()
                                   if Path(k).name == path.name}
                if expected_hashes != {digest}:
                    parser.error(f"label/cache hash mismatch for segment {segment}")
        hashes[path.as_posix()] = digest
        payloads[segment] = json.loads(path.read_text(encoding="utf-8"))
    results = benchmark(payloads, rows, dev_segments)
    gates = {split: passes_gate(results["baseline"][split], results["refined"][split])
             and results["baseline"][split]["unassigned_players"] == results["refined"][split]["unassigned_players"]
             for split in ("development", "control") if split in results["baseline"]}
    report = {"development_segments": sorted(dev_segments), "control_segments": sorted(control_segments),
              "metric_scope": "direct visual shirt labels; one match, one reviewer, correlated frames",
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
