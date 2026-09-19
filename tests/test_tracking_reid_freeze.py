"""The new optional tracker must not weaken the old freeze or its evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.soccertrack_v2.export_joint_identity import (
    DEFAULT_AMENDMENT,
    PREVIOUS_AMENDMENT_SHA256,
    PREVIOUS_CONSENSUS_AMENDMENT_SHA256,
    PREVIOUS_REID_AMENDMENT_SHA256,
    ROI_INTEGRATION_ALLOWLIST,
    digest,
    verify_frozen_code,
)


def test_repository_reid_amendment_preserves_old_artifacts_and_default_parity():
    freeze = Path("docs/measurements/joint-identity-frozen-decision.json")
    verified = verify_frozen_code(freeze)
    amendment = json.loads(DEFAULT_AMENDMENT.read_text(encoding="utf-8"))
    assert amendment["version"] == 4
    previous_path = Path(amendment["previous_amendment"]["path"])
    assert digest(previous_path) == PREVIOUS_CONSENSUS_AMENDMENT_SHA256
    previous = json.loads(previous_path.read_bytes())
    reid_path = Path(previous["previous_amendment"]["path"])
    assert digest(reid_path) == PREVIOUS_REID_AMENDMENT_SHA256
    reid = json.loads(reid_path.read_bytes())
    assert digest(Path(reid["previous_amendment"]["path"])) == PREVIOUS_AMENDMENT_SHA256
    assert set(verified["added_integration_code_sha256_lf"]) == ROI_INTEGRATION_ALLOWLIST
    parity = json.loads(Path(verified["parity_evidence"]["path"]).read_text(encoding="utf-8"))
    assert len(parity["comparisons"]) == 22
    assert all(r["equal"] and r["before_sha256"] == r["after_sha256"] for r in parity["comparisons"])


@pytest.mark.parametrize("corruption", ["previous", "version", "missing_backend"])
def test_new_amendment_rejects_provenance_changes(tmp_path, corruption):
    amendment = json.loads(DEFAULT_AMENDMENT.read_text(encoding="utf-8"))
    if corruption == "previous":
        amendment["previous_amendment"]["sha256"] = "0" * 64
    elif corruption == "version":
        amendment["version"] = 5
    else:
        amendment["added_integration_code_sha256_lf"].pop("app/tracking/deepocsort.py")
    path = tmp_path / "amendment.json"
    path.write_text(json.dumps(amendment), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_frozen_code(Path("docs/measurements/joint-identity-frozen-decision.json"), path)
