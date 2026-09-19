"""Evaluate visually labelled person associations on identical detection boxes.

This is a sparse pair audit, not full-video MOT/IDF1 ground truth. Unlabelled
objects are outside its scope. Missing or ambiguous boxes never count as a
successful association; coverage is reported alongside same/different scores.
Labels identify detections by frame and exact source box, not predicted track ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(labels: dict[str, Any], payloads: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Score exact-box associations without using labels to match identities."""
    samples: dict[tuple[int, int], dict[str, Any]] = {}
    for segment, payload in payloads.items():
        for sample in payload["samples"]:
            key = (segment, int(sample["frame_idx"]))
            if key in samples:
                raise ValueError(f"duplicate frame: {key}")
            samples[key] = sample
    observations: dict[str, tuple[int, int, int] | None] = {}
    missing = Counter()
    for obs in labels["observations"]:
        oid = obs["id"]
        if oid in observations:
            raise ValueError(f"duplicate observation: {oid}")
        box = np.asarray(obs["bbox"], dtype=float)
        if box.shape != (4,) or not np.all(np.isfinite(box)) or np.any(box[2:] <= box[:2]):
            raise ValueError(f"invalid box: {oid}")
        segment, frame = int(obs["segment"]), int(obs["frame_idx"])
        sample = samples.get((segment, frame))
        matches = [] if sample is None else [
            row for row in sample["persons"]
            if np.allclose(row[1:5], box, atol=1e-5, rtol=0)
        ]
        if len(matches) != 1:
            observations[oid] = None
            missing["missing" if not matches else "ambiguous"] += 1
        else:
            assert sample is not None
            observations[oid] = (segment, int(sample.get("continuity_id", 0)), int(matches[0][0]))
    counts: Counter[str] = Counter()
    outcomes = []
    seen_pairs = set()
    for pair in labels["pairs"]:
        left, right, relation = pair["left"], pair["right"], pair["relation"]
        if left == right or left not in observations or right not in observations:
            raise ValueError(f"invalid pair: {pair}")
        key = tuple(sorted((left, right)))
        if key in seen_pairs:
            raise ValueError(f"duplicate pair: {key}")
        seen_pairs.add(key)
        if relation not in ("same", "different", "uncertain"):
            raise ValueError(f"invalid relation: {relation}")
        if relation == "uncertain":
            counts["uncertain_excluded"] += 1
            continue
        counts[f"{relation}_pairs"] += 1
        a, b = observations[left], observations[right]
        linked = None if a is None or b is None else a == b
        passed = linked is not None and linked == (relation == "same")
        counts[f"{relation}_correct"] += int(passed)
        if linked is None:
            counts[f"{relation}_uncovered"] += 1
        elif not passed:
            counts["false_split" if relation == "same" else "false_join"] += 1
        outcomes.append({"left": left, "right": right, "relation": relation,
                         "linked": linked, "passed": passed})
    return {
        "metric_scope": "visually labelled sparse detection pairs; not full-video MOT or IDF1",
        "exact_source_boxes_required": True,
        "observations": len(observations),
        "covered_observations": sum(value is not None for value in observations.values()),
        "missing_observations": missing["missing"],
        "ambiguous_observations": missing["ambiguous"],
        "counts": dict(counts),
        "same_person_recall": counts["same_correct"] / counts["same_pairs"] if counts["same_pairs"] else None,
        "different_person_separation": counts["different_correct"] / counts["different_pairs"] if counts["different_pairs"] else None,
        "outcomes": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists; preserve previous measurements")
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    paths = {int(obs["segment"]): args.cache / f"seg_{int(obs['segment']):04d}.json"
             for obs in labels["observations"]}
    payloads = {segment: json.loads(path.read_text(encoding="utf-8")) for segment, path in paths.items()}
    report = evaluate(labels, payloads)
    report["label_sha256"] = digest(args.labels)
    report["cache_sha256"] = {str(path): digest(path) for path in paths.values()}
    report["evaluator_sha256"] = hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "outcomes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
