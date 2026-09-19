"""Development-only association hypotheses; no source-box removal or defaults.

Compare legal-edge assignment and top/height consistency on the known full
warmup fixtures. These geometric cues are hypotheses, not body-part labels.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scripts.soccertrack_v2.audit_identity_failures import (
    CASES,
    FIXTURES,
    digest,
    load_fixture,
    replay_case,
)


def constrained_assignment(utility: np.ndarray, eligible: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Maximize eligible match count, then utility; forbidden edges cannot steal.

    Dummy columns permit every detection to remain unmatched. Input utilities
    are bounded before the cardinality bonus so even negative legal edges can
    be selected without admitting a forbidden edge.
    """
    from scipy.optimize import linear_sum_assignment

    n, m = utility.shape
    if eligible.shape != utility.shape or not np.isfinite(utility).all():
        raise ValueError("Finite utility and matching eligibility shape required")
    if not n or not m:
        return np.empty((0, 2), dtype=int), np.arange(n), np.arange(m)
    bonus = 2 * min(n, m) + 1
    values = np.full((n, m + n), -bonus * (n + m + 1), dtype=float)
    values[:, m:] = 0
    scaled = utility / max(1., float(np.max(np.abs(utility))))
    values[:, :m] = np.where(eligible, bonus + scaled, values[:, :m])
    rows, cols = linear_sum_assignment(-values)
    matches = np.array([(i, j) for i, j in zip(rows, cols, strict=True)
                        if j < m and eligible[i, j]], dtype=int).reshape(-1, 2)
    return matches, np.setdiff1d(np.arange(n), matches[:, 0]), np.setdiff1d(np.arange(m), matches[:, 1])


def quality_associate(*args, mode: str = "legal"):
    from app.tracking._vendor.deepocsort.association import (
        associate as original_associate,
    )
    from app.tracking._vendor.deepocsort.association import (
        compute_aw_new_metric,
        iou_batch,
        speed_direction_batch,
    )

    det, predicted, det_emb, trk_emb, threshold, velocity, previous, inertia, weight, aw_off, aw, emb_off, grid_off = args
    if mode not in ("legal", "shape", "shape_gate", "shape_guard", "local_guard"):
        raise ValueError("Unknown association hypothesis")
    if not grid_off:
        raise ValueError("Only whole-body embeddings supported")
    overlaps = iou_batch(det, predicted)
    if not len(det) or not len(predicted):
        return constrained_assignment(overlaps, overlaps >= threshold)
    dy, dx = speed_direction_batch(det, previous)
    cosine = np.clip(velocity[:, 0, None] * dy + velocity[:, 1, None] * dx, -1, 1)
    angle = ((np.pi / 2 - np.arccos(cosine)) / np.pi).T
    valid = previous[:, 4] >= 0
    utility = overlaps + angle * inertia * det[:, 4, None] * valid[None, :]
    if not emb_off:
        appearance = det_emb @ trk_emb.T
        weights = weight if aw_off else compute_aw_new_metric(appearance, weight, aw)
        utility += appearance * weights
    eligible = overlaps >= threshold
    if mode != "legal":
        height = np.maximum(predicted[:, 3] - predicted[:, 1], 1)
        ratio = (det[:, 3] - det[:, 1])[:, None] / height[None, :]
        top_error = np.abs(det[:, 1, None] - predicted[None, :, 1]) / height[None, :]
        if mode == "local_guard":
            original = original_associate(*args)
            supports = (overlaps >= .15) & (top_error <= .15) & (ratio >= .65) & (ratio <= 1.5) & valid[None, :]
            lower = (overlaps >= threshold) & (top_error > .2)
            support_edges = np.zeros_like(eligible)
            lower_edges = np.zeros_like(eligible)
            areas = (det[:, 2] - det[:, 0]) * (det[:, 3] - det[:, 1])
            for track in np.flatnonzero(np.any(supports, axis=0) & np.any(lower, axis=0)):
                for upper in np.flatnonzero(supports[:, track]):
                    for part in np.flatnonzero(lower[:, track]):
                        intersection = np.maximum(np.minimum(det[upper, 2:4], det[part, 2:4])
                                                  - np.maximum(det[upper, :2], det[part, :2]), 0).prod()
                        if (intersection / min(areas[upper], areas[part]) >= .25
                                and det[part, 3] > det[upper, 3] + .1 * height[track]
                                and ratio[part, track] <= ratio[upper, track] * 1.05):
                            support_edges[upper, track] = True
                            lower_edges[part, track] = True
            if not support_edges.any():
                return original
            changed_rows = set(map(int, np.flatnonzero(np.any(support_edges | lower_edges, axis=1))))
            changed_tracks = set(map(int, np.flatnonzero(np.any(support_edges, axis=0))))
            # Preserve the original assignment outside the touched component.
            for d, t in original[0]:
                if int(d) in changed_rows:
                    changed_tracks.add(int(t))
            for d, t in original[0]:
                if int(t) in changed_tracks:
                    changed_rows.add(int(d))
            ri, ti = np.array(sorted(changed_rows)), np.array(sorted(changed_tracks))
            local_utility = (utility - np.minimum(top_error, 1) * 2
                             - np.minimum(np.abs(np.log(ratio)), 1) * .25 + .2 * valid[None, :])
            local_eligible = (eligible | support_edges) & ~lower_edges
            pairs, _, _ = constrained_assignment(local_utility[np.ix_(ri, ti)], local_eligible[np.ix_(ri, ti)])
            kept = [(int(d), int(t)) for d, t in original[0] if int(d) not in changed_rows and int(t) not in changed_tracks]
            kept += [(int(ri[d]), int(ti[t])) for d, t in pairs]
            matches = np.array(kept, dtype=int).reshape(-1, 2)
            return matches, np.setdiff1d(np.arange(len(det)), matches[:, 0]), np.setdiff1d(np.arange(len(predicted)), matches[:, 1])
        # A lower-body box can overlap the prediction while missing its top.
        # Never delete it: it may be a real second person.
        utility -= np.minimum(top_error, 1) * 2 + np.minimum(np.abs(np.log(ratio)), 1) * .25
        if mode in ("shape_gate", "shape_guard"):
            eligible |= ((overlaps >= .15) & (top_error <= .15) & (ratio >= .65)
                         & (ratio <= 1.5) & valid[None, :])
        if mode == "shape_guard":
            supported = eligible & (ratio >= .65) & (ratio <= 1.5) & (top_error <= .15)
            partial = (ratio < .65) & (top_error > .3)
            eligible &= ~(partial & np.any(supported, axis=0)[None, :])
            utility += .2 * valid[None, :]
    return constrained_assignment(utility, eligible)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--full", action="store_true", help="All 11 known clips, motion and OSNet arms")
    parser.add_argument("--mode", choices=["shape_guard", "local_guard"], default="local_guard")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    from app.tracking._vendor.deepocsort import ocsort

    hashes = {str(p): digest(p) for p in [Path(__file__), *FIXTURES.glob("*.json.gz")]}
    if args.full:
        from scripts.soccertrack_v2 import benchmark_deepocsort

        def guarded(*values):
            return quality_associate(*values, mode=args.mode)
        with (patch.object(ocsort, "associate", side_effect=guarded),
              patch.object(sys, "argv", ["benchmark_deepocsort", "--out", str(args.out)])):
            benchmark_deepocsort.main()
        report_path = args.out / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["association_experiment"] = dict(mode=args.mode, scope=__doc__, hashes=hashes,
            note="deepocsort_motion/deepocsort names here use the experimental association, not the original adapter profile")
        if hashes != {name: digest(Path(name)) for name in hashes}:
            raise ValueError("Experiment changed during full comparison")
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return
    args.out.mkdir(parents=True)
    results = {}
    for name in CASES:
        source = load_fixture(FIXTURES / f"{name}.json.gz")
        results[name] = {}
        for mode in ("legal", "shape", "shape_gate", "shape_guard", "local_guard"):
            def associate(*values, mode=mode):
                return quality_associate(*values, mode=mode)
            with patch.object(ocsort, "associate", side_effect=associate):
                run = replay_case(source)
            for frame in run["first_stage"]:
                for row in frame["candidates"]:
                    row["baseline_iou_eligible"] = row.pop("geometrically_eligible")
            run["association_mode"] = mode
            results[name][mode] = {k: v for k, v in run.items() if k not in ("frames", "first_stage")}
            (args.out / f"{name}-{mode}.json").write_text(json.dumps(run) + "\n", encoding="utf-8")
            print(name, mode, run["endpoint_ids"], run["linked"], flush=True)
    if hashes != {name: digest(Path(name)) for name in hashes}:
        raise ValueError("Experiment inputs changed during run")
    (args.out / "report.json").write_text(json.dumps(dict(
        scope=__doc__, hashes=hashes, results=results, new_control_opened=False,
        production_changed=False), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
