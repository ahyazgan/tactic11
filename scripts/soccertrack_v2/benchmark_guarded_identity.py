"""Compare identity candidates on all 19 consumed clips; never a fresh control."""

from __future__ import annotations

import argparse
import gc
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.tracking.deepocsort import DEFAULT_MODEL
from app.tracking.teams import TeamAssigner
from scripts.soccertrack_v2 import benchmark_deepocsort
from scripts.soccertrack_v2.benchmark_deepocsort import VIDEO_DIRS
from scripts.soccertrack_v2.benchmark_deepocsort import replay as secondary_replay
from scripts.soccertrack_v2.benchmark_short_gap_motion import (
    DOC,
    SingleThreadVideoReplay,
    annotations,
    compact_score,
    compare_scores,
    configurations,
    coverage,
    recovery_replay,
)
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    box_key,
    digest,
    load,
    predictions,
    score_pairs,
    score_rows,
    source_boxes,
)
from scripts.soccertrack_v2.benchmark_tracker_backends import replay as baseline_replay
from scripts.soccertrack_v2.candidates.guarded_identity_v2 import partition
from scripts.soccertrack_v2.candidates.palette_motion_partitions_v1 import (
    partition as previous_partition,
)
from scripts.soccertrack_v2.short_gap_replay_cache import SecondaryCache, local_path

METHODS = ("baseline", "legacy_palette", "short_gap_v1", "combined")


def baseline_palette(raw, baseline, anchors):
    """Recover the original fitted centers before any IDs or teams change."""
    teams = TeamAssigner()
    for identity, colors in raw["colors"].items():
        for color in colors:
            teams.observe(int(identity), np.asarray(color))
    assignment = teams.fit(
        anchors, eligible_tracks={p[0] for s in baseline["samples"] for p in s["persons"]}
    )
    if any(
        assignment.team_by_track.get(p[0]) != s["person_teams"].get(str(p[0]))
        for s in baseline["samples"]
        for p in s["persons"]
    ):
        raise ValueError("Palette must reproduce the unchanged baseline team evidence")
    return assignment.centers


def known_configurations():
    configs = configurations()
    for group, segments in (("day", [60, 62]), ("night", [80, 82])):
        configs["consensus_" + group] = dict(
            segments=segments,
            cache=f"data/tracking/bench/consensus_control_v1/{group}/raw",
            labels=[f"identity-consensus-control-{group}-labels"],
            pairs=[f"identity-consensus-control-{group}-pairs"],
            anchor=f"joint-identity-development-{group}-results",
        )
    return configs


def verify_old_sources(read):
    freeze = Path("docs/measurements/identity-consensus-frozen-decision.json")
    read(freeze)
    for group in ("day", "night"):
        root = Path("data/tracking/bench/consensus_control_v1") / group
        for path in (root / "raw/manifest.json", root / "label-seal.json"):
            record = read(path)
            if record["freeze_sha256"] != digest(freeze):
                raise ValueError("Old consensus evidence points to a different freeze")
            for name, sha in record.get("video_sha256", record.get("label_sha256", {})).items():
                if digest(local_path(name)) != sha:
                    raise ValueError(f"Old evidence changed: {name}")


def boundary_witnesses(group, segment, baseline, candidate, old_report):
    """Check source boxes on both sides of every previous accepted/rejected split."""
    historical_group = group.replace("consensus_", "closed_")
    record = next(
        (
            r
            for r in old_report["development"]["reports"]
            if r["group"] == historical_group and r["segment"] == segment
        ),
        None,
    )
    if record is None:
        return []
    candidate_ids = {
        (s.get("continuity_id", 0), s["order"], tuple(p[1:5])): p[0]
        for s in candidate["samples"]
        for p in s["persons"]
    }
    checks = []
    for choice in record["choices"]:
        boundary = choice["boundary"]
        observations = [
            (s["order"], (s.get("continuity_id", 0), s["order"], tuple(p[1:5])))
            for s in baseline["samples"]
            for p in s["persons"]
            if s.get("continuity_id", 0) == boundary["continuity_id"] and p[0] == boundary["raw_id"]
        ]
        left = [key for order, key in observations if order < boundary["first_order"]][-3:]
        right = [
            key
            for order, key in observations
            if boundary["first_order"] <= order <= boundary["confirmed_order"]
        ]
        left_ids = {candidate_ids.get(k) for k in left}
        right_ids = {candidate_ids.get(k) for k in right}
        complete = len(left) == 3 and len(right) >= 3 and None not in left_ids | right_ids
        stable = len(left_ids) == len(right_ids) == 1
        preserved = complete and stable and ((left_ids != right_ids) == choice["accepted"])
        checks.append(
            dict(
                boundary=boundary,
                expected_split=choice["accepted"],
                complete=complete,
                left_ids=sorted(left_ids, key=str),
                right_ids=sorted(right_ids, key=str),
                preserved=preserved,
            )
        )
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--secondary-report", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    if version("supervision") != "0.30.2" or version("trackers") != "2.6.0":
        parser.error("Pinned research tracker versions required")
    import cv2
    import torch

    cv2.setNumThreads(1)
    torch.set_grad_enabled(False)
    versions = {
        n: version(n) for n in ("supervision", "trackers", "numpy", "scipy", "torch", "filterpy")
    }
    caches = [SecondaryCache(path, versions) for path in args.secondary_report]
    hashes, outputs, results = {}, {}, {}

    def remember(path):
        hashes[str(path)] = digest(path)

    def read(path):
        remember(path)
        return load(path)

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2 if path.name.endswith("report.json") else None) + "\n",
            encoding="utf-8",
        )
        outputs[str(path)] = digest(path)

    for path in [
        Path(__file__),
        Path(DEFAULT_MODEL),
        *args.secondary_report,
        *Path("app/tracking").rglob("*.py"),
        *Path("scripts/soccertrack_v2").glob("benchmark_*.py"),
        *Path("scripts/soccertrack_v2/candidates").glob("*.py"),
        Path("scripts/soccertrack_v2/short_gap_replay_cache.py"),
    ]:
        remember(path)
    old_report = read(DOC / "identity-palette-development-results.json")
    # The previously accepted/rejected boundaries are immutable development
    # witnesses. Check their original raw-cache provenance before using them.
    for name, sha in old_report["development"]["hashes"].items():
        path = local_path(name)
        if path.suffix == ".json" and "seg_" in path.name:
            if digest(path) != sha:
                raise ValueError(f"Old boundary evidence changed: {name}")
            remember(path)
    verify_old_sources(read)
    args.out.mkdir(parents=True)
    started = datetime.now(UTC).isoformat()
    for group, cfg in known_configurations().items():
        raw = {s: read(Path(cfg["cache"]) / f"seg_{s:04d}.json") for s in cfg["segments"]}
        available = source_boxes(raw)
        anchors = np.asarray(read(DOC / f"{cfg['anchor']}.json")["anchors"]["before"])
        rows, pairs = annotations(group, cfg, read)
        if any((r["segment"], box_key(r["frame_idx"], r["bbox"])) not in available for r in rows):
            raise ValueError("Kit label missing from source")
        payloads, segments = {m: {} for m in METHODS}, {}
        for segment, data in raw.items():
            video = (
                Path(data["video"])
                if group.startswith(("palette_", "consensus_"))
                else Path(VIDEO_DIRS[group]) / f"seg_{segment:04d}.mp4"
            )
            remember(video)
            write(
                args.out / "partial-report.json",
                dict(
                    started_at_utc=started,
                    complete=False,
                    input_code_sha256=hashes.copy(),
                    output_sha256=outputs.copy(),
                    versions=versions,
                    results=results,
                ),
            )
            base, base_stats = baseline_replay(data, "supervision", anchors)
            baseline_centers = baseline_palette(data, base, anchors)
            recovered, recovery_stats = recovery_replay(data, anchors)
            matching = [
                c
                for c in caches
                if str(segment) in c.report["results"].get(group, {}).get("segments", {})
            ]
            if len(matching) > 1:
                raise ValueError("Multiple cached secondary sources for one clip")
            if matching:
                support, secondary_stats = matching[0].read(group, segment)
            else:
                with patch.object(benchmark_deepocsort, "VideoReplay", SingleThreadVideoReplay):
                    support, secondary_stats = secondary_replay(data, "deepocsort", anchors, video)
                secondary_stats["decoder_threads"] = 1
            legacy, legacy_events = partition(
                data,
                base,
                support,
                base,
                anchors,
                baseline_centers=baseline_centers,
                appearance_only=True,
            )
            previous, previous_events = previous_partition(data, recovered, support, base, anchors)
            combined, events = partition(
                data, recovered, support, base, anchors, baseline_centers=baseline_centers
            )
            values = dict(
                baseline=base, legacy_palette=legacy, short_gap_v1=previous, combined=combined
            )
            for method, payload in {**values, "secondary": support}.items():
                write(args.out / group / method / f"seg_{segment:04d}.json", payload)
            for method, payload in values.items():
                payloads[method][segment] = payload
            segments[str(segment)] = dict(
                baseline=base_stats,
                recovery=recovery_stats,
                secondary=secondary_stats,
                boundaries=events,
                legacy_boundaries=legacy_events,
                palette_provenance=dict(
                    fixed_anchors=anchors.tolist(),
                    baseline_centers=baseline_centers.tolist()
                    if baseline_centers is not None
                    else None,
                    note="Appearance uses original fitted centers; crossover uses fixed anchors. No refit after motion or partition.",
                ),
                previous_boundaries=previous_events,
                coverage=coverage(base, combined),
                recovery_selection=combined.get("recovery_fallback", dict(selected="motion")),
                boundary_witnesses={
                    m: boundary_witnesses(group, segment, base, p, old_report)
                    for m, p in values.items()
                    if m != "baseline"
                },
            )
            write(args.out / group / f"seg_{segment:04d}-audit.json", segments[str(segment)])
            gc.collect()
            torch.cuda.empty_cache()
            print(
                group,
                segment,
                "motion",
                len(recovery_stats["events"]),
                "boundaries",
                len(events),
                flush=True,
            )
        scores = {
            m: dict(
                kit=score_rows(rows, predictions(p), blue=0),
                pairs={name: score_pairs(label, p, available) for name, label in pairs.items()},
            )
            for m, p in payloads.items()
        }
        results[group] = {m: compact_score(s, scores["baseline"]) for m, s in scores.items()}
        results[group]["combined"]["regressions_vs_previous"] = {
            method: compare_scores(scores[method], scores["combined"])
            for method in ("legacy_palette", "short_gap_v1")
        }
        results[group]["segments"] = segments
        print(group, "regressions", results[group]["combined"]["regressions"], flush=True)
    for path, sha in hashes.items():
        if digest(Path(path)) != sha:
            raise ValueError(f"Input changed during replay: {path}")
    for cache in caches:
        cache.validate()
    # A partial report is not registered as a stable output of the completed run.
    outputs.pop(str(args.out / "partial-report.json"), None)
    report = dict(
        started_at_utc=started,
        completed_at_utc=datetime.now(UTC).isoformat(),
        scope=__doc__,
        input_code_sha256=hashes,
        output_sha256=outputs.copy(),
        versions=versions,
        results=results,
    )
    witnesses = [
        w
        for group in results.values()
        for segment in group["segments"].values()
        for w in segment["boundary_witnesses"]["combined"]
    ]
    report["development_acceptance"] = dict(
        old_boundaries_pass=(
            len(witnesses) == 7
            and sum(w["expected_split"] for w in witnesses) == 6
            and all(w["preserved"] for w in witnesses)
        ),
        source_coverage_pass=all(
            s["coverage"]["removed"] == s["coverage"]["changed_teams"] == 0
            for g in results.values()
            for s in g["segments"].values()
        ),
        sparse_regressions_pass=all(
            not g["combined"]["regressions"]
            and not any(g["combined"]["regressions_vs_previous"].values())
            for g in results.values()
        ),
        independent_control=False,
        live_integration=False,
    )
    write(args.out / "report.json", report)
    print("REPORT", args.out / "report.json", flush=True)


if __name__ == "__main__":
    main()
