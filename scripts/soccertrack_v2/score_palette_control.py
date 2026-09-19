"""Score sealed controls with the original frozen evaluators; never tune on controls."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from scripts.soccertrack_v2.benchmark_joint_identity import predictions, score_pairs, source_boxes
from scripts.soccertrack_v2.benchmark_track_buffer import score_rows
from scripts.soccertrack_v2.benchmark_tracker_backends import regressions
from scripts.soccertrack_v2.consensus_palette_control import (
    FREEZE,
    ROOT,
    digest,
    load,
    verify,
    write_new,
)


def evaluate(group: str, decision: dict) -> dict:
    root = ROOT / group
    seal_path = root / "label-seal.json"
    seal = load(seal_path)
    if seal["freeze_sha256"] != digest(FREEZE):
        raise ValueError("Wrong freeze")
    for name, expected in seal["label_sha256"].items():
        if digest(Path(name)) != expected:
            raise ValueError("Sealed labels changed")
    manifest = load(root / "predictions/manifest.json")
    if manifest != dict(freeze_sha256=digest(FREEZE), label_seal_sha256=digest(seal_path), source_evidence_exact=True):
        raise ValueError("Replay does not match sealed labels")
    documents = [load(Path(name)) for name in seal["label_sha256"]]
    labels = next(d for d in documents if "records" in d)
    pairs = next(d for d in documents if "pairs" in d)
    segments = [int(s) for s in decision["groups"][group]["segments"]]
    available = source_boxes({s: load(root / "raw" / f"seg_{s:04d}.json") for s in segments})
    results, boundaries, hashes = {}, [], {}
    for backend in ("supervision", "consensus", "palette"):
        payloads = {}
        for segment in segments:
            path = root / "predictions" / backend / f"seg_{segment:04d}.json"
            payloads[segment] = load(path)
            hashes[str(path)] = digest(path)
            if backend in {"consensus", "palette"}:
                def visit(value, segment=segment, backend=backend):
                    if isinstance(value, dict):
                        if "identity_consensus" in value:
                            boundaries.extend(dict(backend=backend, segment=segment, **b) for b in value["identity_consensus"]["boundaries"])
                        for child in value.values():
                            visit(child)
                    elif isinstance(value, list):
                        for child in value:
                            visit(child)
                visit(payloads[segment]["summary"])
        pred = predictions(payloads)
        results[backend] = dict(kit=score_rows(labels["records"], pred, blue=0),
            pairs={"control": score_pairs(pairs, payloads, available)},
            output_observations=sum(len(s["persons"]) for p in payloads.values() for s in p["samples"]))
    failures = regressions(results["supervision"], results["palette"])
    previous_failures = regressions(results["consensus"], results["palette"])
    for metric in ("conflicting_track_labels", "not_person_remaining"):
        if results["palette"]["kit"][metric] > results["supervision"]["kit"][metric]:
            failures.append("kit." + metric)
    if results["palette"]["output_observations"] < results["supervision"]["output_observations"]:
        failures.append("output_observations")
    for metric in ("conflicting_track_labels", "not_person_remaining"):
        if results["palette"]["kit"][metric] > results["consensus"]["kit"][metric]:
            previous_failures.append("kit." + metric)
    if results["palette"]["output_observations"] < results["consensus"]["output_observations"]:
        previous_failures.append("output_observations")
    return dict(results=results, regressions=failures, previous_consensus_regressions=previous_failures, boundaries=boundaries,
        boundary_review_required=bool(boundaries), prediction_sha256=hashes,
        label_seal_sha256=digest(seal_path), blue_slot=0, slot_source="frozen development anchors",
        source_review_counts=dict(Counter(r["status"] for r in labels["source_review"])),
        kit_label_counts=dict(Counter(r["kit"] for r in labels["records"])),
        limitations=labels["limitations"], independently_adjudicated=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["day", "night"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh report required")
    decision = verify()
    report = evaluate(args.group, decision)
    report["freeze_sha256"] = digest(FREEZE)
    report["scorer_sha256"] = digest(Path(__file__))
    report["promotion"] = "Not authorized by sparse scores alone; all boundaries require source review and a positive control correction."
    verify()
    write_new(args.out, report)
    print({k: report[k] for k in ("regressions", "boundaries", "source_review_counts")})


if __name__ == "__main__":
    main()
