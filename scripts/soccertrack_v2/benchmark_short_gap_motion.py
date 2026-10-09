"""Replay a research-only short-gap/palette candidate on all 15 consumed clips.

All source detections, labels, anchors and videos are read-only. Secondary
Deep OC-SORT evidence is recomputed from source pixels, with the pinned OSNet
model. This retrospective experiment is not a production backend or control.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from app.tracking.deepocsort import DEFAULT_MODEL
from scripts.soccertrack_v2 import benchmark_deepocsort
from scripts.soccertrack_v2.benchmark_deepocsort import VIDEO_DIRS, VideoReplay
from scripts.soccertrack_v2.benchmark_deepocsort import replay as secondary_replay
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    EvidenceTracker,
    adjudicated_rows,
    backend_settings,
    box_key,
    digest,
    groups,
    load,
    pair_subset,
    predictions,
    regressions,
    retrack,
    score_pairs,
    score_rows,
    source_boxes,
)
from scripts.soccertrack_v2.benchmark_tracker_backends import replay as baseline_replay
from scripts.soccertrack_v2.candidates.palette_motion_partitions_v1 import partition
from scripts.soccertrack_v2.candidates.short_gap_motion_v1 import ShortGapMotionTracker
from scripts.soccertrack_v2.short_gap_replay_cache import SecondaryCache

DOC = Path("docs/measurements")
METHODS = ("baseline", "recovery_refit", "preserved", "partitioned")


class SingleThreadVideoReplay(VideoReplay):
    """Set the decoder option explicitly; the environment hint is not sufficient."""

    def __init__(self, tracker, video, samples):
        import cv2

        self.tracker = tracker
        self.cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        if not self.cap.isOpened() or self.cap.get(cv2.CAP_PROP_N_THREADS) != 1:
            self.cap.release()
            raise ValueError("A verified single-thread video decoder is required")
        self.samples = iter(samples)
        self.frame = -1
        self.max_time_lost = tracker.max_time_lost
        self.update_seconds = []


def configurations():
    configs = groups()
    for group in ("day", "night"):
        configs["palette_" + group] = dict(
            segments=[64, 66] if group == "day" else [78, 84],
            cache=f"data/tracking/bench/consensus_palette_control_v1/{group}/raw",
            labels=[f"identity-palette-control-{group}-labels"],
            pairs=[f"identity-palette-control-{group}-pairs"],
            anchor=f"joint-identity-development-{group}-results",
        )
    return configs


def annotations(group, cfg, read):
    rows = [r for name in cfg["labels"] for r in read(DOC / f"{name}.json")["records"]]
    excluded = set()
    if group == "day":
        rows = adjudicated_rows(rows, [read(DOC / "identity-kit-label-adjudication.json")])
        parts = read(DOC / "duplicate-part-development-labels.json")["records"]
        parts += [
            r
            for r in read(DOC / "joint-identity-control-day-pairs.json")["observations"]
            if r.get("duplicate_part_of")
        ]
        excluded = {(r["segment"], box_key(r["frame_idx"], r["bbox"])) for r in parts}
        rows += read(DOC / "joint-identity-control-day-labels.json")["records"]
        rows = [
            r for r in rows if (r["segment"], box_key(r["frame_idx"], r["bbox"])) not in excluded
        ]
    labels = {name: pair_subset(read(DOC / f"{name}.json"), excluded) for name in cfg["pairs"]}
    if group == "palette_day":
        # Explicitly post-unblinding: never overwrite the original sealed labels.
        errata = read(DOC / "identity-palette-control-label-errata-20261009.json")
        for correction in errata["corrections"]:
            for pair in labels["identity-palette-control-day-pairs"]["pairs"]:
                if pair["left"] == correction["left"]:
                    pair["right"] = (
                        correction["corrected_same_right"]
                        if pair["relation"] == "same"
                        else correction["recomputed_negative_right"]
                    )
    return rows, labels


def recovery_replay(raw, anchors):
    import supervision as sv

    primary = sv.ByteTrack(**backend_settings(raw, "supervision"))
    candidate = ShortGapMotionTracker(primary)

    class SourceStream:
        max_time_lost = primary.max_time_lost

        def update_with_detections(self, detections):
            source = raw["detected_persons"][str(primary.frame_id)]
            colors = [source[int(i)]["color"] for i in detections.data["raw_index"]]
            return candidate.update_with_detections(detections, colors)

    checked = EvidenceTracker(SourceStream(), external=False)
    started = perf_counter()
    with patch.object(sv, "ByteTrack", return_value=checked):
        samples, teams, stats = retrack(raw, correct_buffer=False)
    assignment = teams.fit(anchors, eligible_tracks={r[0] for s in samples for r in s.persons})
    for sample in samples:
        sample.person_teams = {
            str(r[0]): assignment.team_by_track.get(r[0]) for r in sample.persons
        }
    stats.update(
        elapsed_seconds=perf_counter() - started,
        events=candidate.events,
        tracking_update_ms=dict(
            mean=float(np.mean(checked.update_seconds)) * 1000,
            p95=float(np.percentile(checked.update_seconds, 95)) * 1000,
        ),
    )
    return dict(samples=[asdict(s) for s in samples]), stats


def compare_scores(base, candidate):
    failed = regressions(base, candidate)
    for name in ("not_person_remaining", "conflicting_track_labels"):
        if candidate["kit"][name] > base["kit"][name]:
            failed.append("kit." + name)
    return failed


def compact_score(score, baseline):
    output = dict(kit=score["kit"], pairs={})
    for name, pairs in score["pairs"].items():
        prior = {(p["left"], p["right"]): p for p in baseline["pairs"][name]["outcomes"]}
        output["pairs"][name] = {k: v for k, v in pairs.items() if k != "outcomes"}
        output["pairs"][name]["changed_outcomes"] = [
            dict(before=prior[(p["left"], p["right"])], after=p)
            for p in pairs["outcomes"]
            if p != prior[(p["left"], p["right"])]
        ]
    output["regressions"] = compare_scores(baseline, score)
    return output


def coverage(base, candidate):
    def observations(payload):
        return {
            (s.get("continuity_id", 0), s["frame_idx"], tuple(r[1:])): s["person_teams"].get(
                str(r[0])
            )
            for s in payload["samples"]
            for r in s["persons"]
        }

    before, after = observations(base), observations(candidate)
    return dict(
        baseline=len(before),
        candidate=len(after),
        removed=len(before.keys() - after.keys()),
        added=len(after.keys() - before.keys()),
        changed_teams=sum(before[k] != after[k] for k in before.keys() & after.keys()),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--secondary-report",
        type=Path,
        help="Reuse a completed, hash-verified secondary replay; no model inference",
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    if version("supervision") != "0.30.2" or version("trackers") != "2.6.0":
        parser.error("Pinned supervision==0.30.2 and trackers==2.6.0 required")
    os.environ["OPENCV_FFMPEG_THREADS"] = "1"
    import cv2
    import torch

    cv2.setNumThreads(1)
    torch.set_grad_enabled(False)
    hashes, outputs = {}, {}
    versions = {
        n: version(n) for n in ("supervision", "trackers", "numpy", "scipy", "torch", "filterpy")
    }
    cached = SecondaryCache(args.secondary_report, versions) if args.secondary_report else None

    def remember(path):
        hashes[str(path)] = digest(path)

    def read(path):
        remember(path)
        return load(path)

    for path in [
        Path(__file__),
        Path(DEFAULT_MODEL),
        *Path("app/tracking").rglob("*.py"),
        *Path("scripts/soccertrack_v2").glob("benchmark_*.py"),
        *Path("scripts/soccertrack_v2/candidates").glob("*.py"),
        Path("scripts/soccertrack_v2/short_gap_replay_cache.py"),
    ]:
        remember(path)
    args.out.mkdir(parents=True)
    results = {}
    started = datetime.now(UTC).isoformat()
    if cached:
        remember(args.secondary_report)
    for group, cfg in configurations().items():
        raw = {s: read(Path(cfg["cache"]) / f"seg_{s:04d}.json") for s in cfg["segments"]}
        available = source_boxes(raw)
        anchors = np.asarray(read(DOC / f"{cfg['anchor']}.json")["anchors"]["before"])
        rows, pairs = annotations(group, cfg, read)
        if any((r["segment"], box_key(r["frame_idx"], r["bbox"])) not in available for r in rows):
            raise ValueError("Kit label missing from raw source")
        payloads = {m: {} for m in METHODS}
        segments = {}
        for segment, data in raw.items():
            video = (
                Path(data["video"])
                if group.startswith("palette_")
                else Path(VIDEO_DIRS[group]) / f"seg_{segment:04d}.mp4"
            )
            remember(video)
            # A failed later clip must not erase the provenance of completed ones.
            (args.out / "partial-manifest.json").write_text(
                json.dumps(
                    dict(
                        started_at_utc=started,
                        complete=False,
                        input_code_sha256=hashes,
                        output_sha256=outputs,
                        versions=versions,
                        results=results,
                    ),
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            base, baseline_stats = baseline_replay(data, "supervision", anchors)
            recovered, recovery_stats = recovery_replay(data, anchors)
            if cached:
                support, secondary_stats = cached.read(group, segment)
            else:
                with patch.object(benchmark_deepocsort, "VideoReplay", SingleThreadVideoReplay):
                    support, secondary_stats = secondary_replay(data, "deepocsort", anchors, video)
                secondary_stats["decoder_threads"] = 1
            transformed, events = partition(data, recovered, support, base, anchors)
            preserved, _ = partition(data, recovered, dict(samples=[]), base, anchors)
            values = dict(
                baseline=base,
                recovery_refit=recovered,
                preserved=preserved,
                partitioned=transformed,
            )
            for method, payload in {**values, "secondary": support}.items():
                dest = args.out / group / method / f"seg_{segment:04d}.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                outputs[str(dest)] = digest(dest)
            for method, payload in values.items():
                payloads[method][segment] = payload
            segments[str(segment)] = dict(
                baseline=baseline_stats,
                recovery=recovery_stats,
                secondary=secondary_stats,
                boundaries=events,
                coverage=coverage(base, transformed),
                recovery_selection=transformed.get(
                    "recovery_fallback",
                    dict(selected="motion", reason="baseline_coverage_preserved"),
                ),
                applied_motion_events=0
                if transformed.get("recovery_fallback")
                else len(recovery_stats["events"]),
            )
            (args.out / group / f"seg_{segment:04d}-audit.json").write_text(
                json.dumps(segments[str(segment)], indent=2) + "\n", encoding="utf-8"
            )
            gc.collect()
            torch.cuda.empty_cache()
            print(
                group,
                segment,
                "motion",
                len(recovery_stats["events"]),
                "partitions",
                len(events),
                flush=True,
            )
        scores = {
            m: dict(
                kit=score_rows(rows, predictions(p), blue=0),
                pairs={n: score_pairs(label, p, available) for n, label in pairs.items()},
            )
            for m, p in payloads.items()
        }
        results[group] = {m: compact_score(s, scores["baseline"]) for m, s in scores.items()}
        results[group]["segments"] = segments
        print(
            group,
            "partitioned regressions",
            results[group]["partitioned"]["regressions"],
            flush=True,
        )
    for path, sha in hashes.items():
        if digest(Path(path)) != sha:
            raise ValueError(f"Input changed during replay: {path}")
    if cached:
        cached.validate()
    report = dict(
        started_at_utc=started,
        completed_at_utc=datetime.now(UTC).isoformat(),
        scope="All 15 clips are consumed development data, including disclosed posthoc palette-day errata. Single-AI sparse labels, not MOT ground truth. No fresh control; no production promotion.",
        input_code_sha256=hashes,
        output_sha256=outputs,
        versions=versions,
        results=results,
    )
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("REPORT", args.out / "report.json", flush=True)


if __name__ == "__main__":
    main()
