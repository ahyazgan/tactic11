"""Score sealed guarded controls with unchanged source-box evaluators.

Sparse scores never authorize promotion. Every motion proposal, fallback and
changed partition still requires a separate, explicitly post-prediction review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from scripts.soccertrack_v2.benchmark_short_gap_motion import compare_scores
from scripts.soccertrack_v2.benchmark_tracker_backends import (
    digest,
    load,
    predictions,
    score_pairs,
    score_rows,
    source_boxes,
)
from scripts.soccertrack_v2.guarded_control import (
    FREEZE,
    METHODS,
    ROOT,
    SOURCES,
    seal_path,
    source_coverage,
    verify,
    verify_seals,
    write_new,
)


def scores(payloads, labels, pairs, raws):
    return dict(kit=score_rows(labels["records"], predictions(payloads), blue=0),
        pairs={"control": score_pairs(pairs, payloads, source_boxes(raws))},
        observations=sum(len(s["persons"]) for p in payloads.values() for s in p["samples"]))


def compare(results):
    candidate = results["guarded"]
    output = {}
    for method in ("supervision", "palette"):
        previous = results[method]
        old = {(p["left"], p["right"]): p for p in previous["pairs"]["control"]["outcomes"]}
        changes = [dict(before=old[p["left"], p["right"]], after=p)
            for p in candidate["pairs"]["control"]["outcomes"] if p != old[p["left"], p["right"]]]
        output[method] = dict(regressions=compare_scores(previous, candidate), changed_pairs=changes,
            positive_pair_changes=sum(not c["before"]["passed"] and c["after"]["passed"] for c in changes))
    return output


def evaluate(group, decision):
    verify_seals(decision)
    root = ROOT / group
    seal_record = load(seal_path(group))
    documents = [load(Path(p)) for p in seal_record["label_sha256"]]
    labels = next(d for d in documents if "records" in d)
    pairs = next(d for d in documents if "observations" in d)
    segments = [int(s) for s in decision["groups"][group]["segments"]]
    raws = {s: load(root / "raw" / f"seg_{s:04d}.json") for s in segments}
    manifest = load(root / "predictions/manifest.json")
    expected = {root / "predictions" / m / f"seg_{s:04d}.json" for m in METHODS for s in segments}
    hashes = {Path(p).resolve(): sha for p, sha in manifest["output_sha256"].items()}
    if (manifest["freeze_sha256"] != digest(FREEZE)
            or manifest["label_seal_sha256"] != {g: digest(seal_path(g)) for g in SOURCES}
            or len(hashes) != len(expected) or set(hashes) != {p.resolve() for p in expected}
            or any(digest(p) != sha for p, sha in hashes.items())):
        raise ValueError("Prediction manifest changed or incomplete")
    results, payloads, reviews, coverage = {}, {}, [], []
    for method in METHODS:
        payloads[method] = {s: load(root / "predictions" / method / f"seg_{s:04d}.json") for s in segments}
        results[method] = scores(payloads[method], labels, pairs, raws)
        for segment, payload in payloads[method].items():
            coverage.append(dict(segment=segment, backend=method, coverage=source_coverage(
                raws[segment], payloads["supervision"][segment], payload)))
            if method != "supervision":
                name = "identity_guarded" if method == "guarded" else "identity_consensus"
                audit = payload["summary"]["calibration_stats"][name]
                reviews.append(dict(segment=segment, backend=method, boundaries=audit["boundaries"],
                    motion_proposals=audit.get("motion_proposals", []), recovery_fallback=audit.get("recovery_fallback")))
    if coverage != manifest["comparisons"]:
        # Loop order differs deliberately; compare by explicit source/method key.
        def indexed(rows):
            return {(r["segment"], r["backend"]): r["coverage"] for r in rows}
        if len(manifest["comparisons"]) != len(coverage) or indexed(coverage) != indexed(manifest["comparisons"]):
            raise ValueError("Replay source-coverage audit changed")
    return dict(group=group, results=results, comparisons=compare(results), source_coverage=coverage,
        changes_requiring_source_review=reviews,
        source_review_counts=dict(Counter(r["status"] for r in labels["source_review"])),
        kit_label_counts=dict(Counter(r["kit"] for r in labels["records"])),
        blue_slot=0, slot_source="unchanged development anchors", label_seal_sha256=digest(seal_path(group)),
        prediction_manifest_sha256=digest(root / "predictions/manifest.json"),
        prediction_sha256=manifest["output_sha256"], limitations=labels["limitations"],
        promotion_authorized=False, accuracy_confirmed=False, independently_adjudicated=False,
        scope="Same-match temporal control with sparse source labels. All changes need post-prediction source review; no full-match IDF1/HOTA, ball or live-speed certification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=list(SOURCES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh report required")
    decision = verify()
    report = evaluate(args.group, decision)
    report.update(freeze_sha256=digest(FREEZE), scorer_sha256=digest(Path(__file__)))
    verify()
    verify_seals(decision)
    write_new(args.out, report)
    print(report["comparisons"])


if __name__ == "__main__":
    main()
