"""Prove the default collection path still reproduces all 22 previous payloads.

Only the two new default config fields are removed before byte comparison.
All samples, assignments, colors, calibration, ball fields and statistics must
match. The original freeze, v1 amendment and v1 parity are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from scripts.soccertrack_v2.benchmark_joint_identity import replay
from scripts.soccertrack_v2.benchmark_tracker_backends import digest, load
from scripts.soccertrack_v2.export_joint_identity import (
    INTEGRATION_ALLOWLIST,
    REID_INTEGRATION_ALLOWLIST,
)


def code_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh output directory required")
    args.out.mkdir(parents=True)
    freeze_path = Path("docs/measurements/joint-identity-frozen-decision.json")
    freeze = load(freeze_path)
    expected = freeze["code_sha256_lf"]
    current = {name: code_hash(name) for name in expected}
    added = {name: code_hash(name) for name in sorted(REID_INTEGRATION_ALLOWLIST)}
    if any(current[n] != h for n, h in expected.items() if n not in INTEGRATION_ALLOWLIST):
        raise ValueError("Unrelated frozen classifier code changed")
    comparisons = []
    inputs = {}
    for group in ("day", "night", "night_extra", "night_control"):
        previous = Path(f".cache/kit_joint_agent/production_guard_parity_{group}_v1")
        report = load(previous / "report.json")
        inputs[str(previous / "report.json")] = digest(previous / "report.json")
        for name, value in report["source_sha256"].items():
            if digest(Path(name)) != value:
                raise ValueError(f"Previous input hash changed: {name}")
            inputs[name] = value
        anchors = {"before": None, "after": None}
        if report["anchor_report"]:
            anchor_path = Path(report["anchor_report"])
            inputs[str(anchor_path)] = digest(anchor_path)
            anchors = {n: np.asarray(v) for n, v in load(anchor_path)["anchors"].items()}
        features = [Path(p) for p in report["source_sha256"] if "features" in p and p.endswith(".json")]
        for feature_path in features:
            feature = load(feature_path)
            segment = feature["segment"]
            raw_paths = [Path(p) for p in feature["source_sha256"] if p.endswith(".json")]
            raw = next(p for p in raw_paths if "detected_persons" in load(p))
            for variant, refined in (("before", False), ("after", True)):
                old_path = previous / variant / f"seg_{segment:04d}.json"
                payload = replay(load(raw), feature, refined=refined, anchor=anchors[variant])
                if anchors[variant] is None:
                    anchors[variant] = np.round(np.asarray(payload["assignment"]["centers"]), 1)
                assert payload["config"].pop("tracker_backend") == "supervision"
                assert payload["config"].pop("reid_model") == "data/tracking/models/osnet_ain_ms_d_c.pth.tar"
                target = args.out / group / variant / old_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                equal = target.read_bytes() == old_path.read_bytes()
                if not equal:
                    raise ValueError(f"Default replay differs: {group}/{variant}/{segment}")
                comparisons.append(dict(group=group, variant=variant, segment=segment,
                    before=str(old_path), after=str(target), before_sha256=digest(old_path),
                    after_sha256=digest(target), equal=equal,
                    observations=sum(len(s["persons"]) for s in payload["samples"])))
                print(group, variant, segment, "equal", flush=True)
    if current != {name: code_hash(name) for name in expected} or added != {name: code_hash(name) for name in added}:
        raise ValueError("Code changed during integration replay")
    if inputs != {name: digest(Path(name)) for name in inputs}:
        raise ValueError("Input changed during integration replay")
    result = dict(created_at_utc=datetime.now(UTC).isoformat(), all_equal=True,
        scope=__doc__, comparisons=comparisons, input_sha256=inputs,
        frozen_decision_sha256=digest(freeze_path), frozen_code_sha256_lf=expected,
        amended_code_sha256_lf=current, added_integration_code_sha256_lf=added)
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
