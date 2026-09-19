"""An integration amendment cannot rewrite the frozen identity experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.soccertrack_v2.export_joint_identity import (
    ADDED_INTEGRATION_ALLOWLIST,
    DEFAULT_AMENDMENT,
    INTEGRATION_ALLOWLIST,
    digest,
    frozen_hashes,
    verify_frozen_code,
)

PROTECTED_CODE = "app/tracking/identity_split.py"
FREEZE = Path("docs/measurements/original-freeze.json")
PARITY = Path("docs/measurements/parity.json")


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _code_hash(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


@pytest.fixture
def original_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in {*INTEGRATION_ALLOWLIST, PROTECTED_CODE}:
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Code hashing must be portable across Windows and LF checkouts.
        path.write_bytes(b"first = 1\r\nsecond = 2\r\n")
    hashes = {name: _code_hash(name) for name in sorted({*INTEGRATION_ALLOWLIST, PROTECTED_CODE})}
    _write_json(FREEZE, {"candidate": "original", "code_sha256_lf": hashes})
    return hashes


def _amend(original):
    changes = {}
    for name in sorted(INTEGRATION_ALLOWLIST):
        Path(name).write_text("first = 1\nsecond = 2\nintegration = 3\n", encoding="utf-8")
        changes[name] = {
            "before_sha256_lf": original[name], "after_sha256_lf": _code_hash(name),
            "reason": "Preserve explicit recorded/live integration parity",
        }
    added = {}
    for name in sorted(ADDED_INTEGRATION_ALLOWLIST):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("integration_evidence = 1\n", encoding="utf-8")
        added[name] = _code_hash(name)
    amended = {name: changes[name]["after_sha256_lf"] if name in changes else value
               for name, value in original.items()}
    _write_json(PARITY, {
        "all_equal": True, "frozen_decision_sha256": digest(FREEZE),
        "frozen_code_sha256_lf": original, "amended_code_sha256_lf": amended,
        "added_integration_code_sha256_lf": added,
    })
    amendment = {
        "original_freeze": {"path": FREEZE.as_posix(), "sha256": digest(FREEZE)},
        "code_changes": changes,
        "added_integration_code_sha256_lf": added,
        "parity_evidence": {"path": PARITY.as_posix(), "sha256": digest(PARITY)},
    }
    _write_json(DEFAULT_AMENDMENT, amendment)
    return amendment


def test_original_tree_needs_no_amendment_and_reports_original_match(original_tree):
    assert not DEFAULT_AMENDMENT.exists()
    assert frozen_hashes(FREEZE) == original_tree
    verification = verify_frozen_code(FREEZE)
    assert verification["mode"] == "original_freeze"
    assert verification["matches_original_freeze"] is True
    assert verification["original_code_sha256_lf"] == verification["production_code_sha256_lf"]
    assert verification["integration_amendment"] is None
    assert verification["parity_evidence"] is None


def test_explicit_patch_keeps_original_immutable_and_reports_distinct_current_provenance(original_tree):
    original_bytes = FREEZE.read_bytes()
    amendment = _amend(original_tree)
    verification = verify_frozen_code(FREEZE)
    assert FREEZE.read_bytes() == original_bytes
    assert verification["mode"] == "integration_amendment"
    assert verification["matches_original_freeze"] is False
    assert verification["original_code_sha256_lf"] == original_tree
    assert verification["production_code_sha256_lf"] != original_tree
    assert frozen_hashes(FREEZE) == verification["production_code_sha256_lf"]
    assert verification["original_freeze"] == amendment["original_freeze"]
    assert verification["integration_amendment"] == {
        "path": DEFAULT_AMENDMENT.as_posix(), "sha256": digest(DEFAULT_AMENDMENT),
    }
    assert verification["parity_evidence"] == amendment["parity_evidence"]
    assert verification["code_changes"] == amendment["code_changes"]
    assert verification["added_integration_code_sha256_lf"] == amendment["added_integration_code_sha256_lf"]
    # Everything outside the three named integration files still matches exactly.
    assert verification["production_code_sha256_lf"][PROTECTED_CODE] == original_tree[PROTECTED_CODE]
    assert json.loads(json.dumps(verification)) == verification  # lossless manifest metadata


def test_changed_tree_requires_amendment_even_when_it_is_explicitly_disabled(original_tree):
    Path("scripts/track_video.py").write_text("changed\n", encoding="utf-8")
    for amendment in (DEFAULT_AMENDMENT, None):
        with pytest.raises(ValueError, match="amendment is required"):
            frozen_hashes(FREEZE, amendment)


def test_protected_algorithm_change_is_rejected_even_with_valid_integration_patch(original_tree):
    _amend(original_tree)
    Path(PROTECTED_CODE).write_text("threshold = 0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="do not match amended hashes.*identity_split.py"):
        verify_frozen_code(FREEZE)


def test_amendment_cannot_authorize_an_extra_algorithm_file(original_tree):
    amendment = _amend(original_tree)
    Path(PROTECTED_CODE).write_text("threshold = 0\n", encoding="utf-8")
    amendment["code_changes"][PROTECTED_CODE] = {
        "before_sha256_lf": original_tree[PROTECTED_CODE], "after_sha256_lf": _code_hash(PROTECTED_CODE),
        "reason": "Attempted experiment change",
    }
    _write_json(DEFAULT_AMENDMENT, amendment)
    with pytest.raises(ValueError, match="exactly the three allowed integration files"):
        verify_frozen_code(FREEZE)


@pytest.mark.parametrize("corruption,match", [
    ("freeze_bytes", "original freeze path or raw digest"),
    ("freeze_digest", "original freeze path or raw digest"),
    ("freeze_path", "original freeze path or raw digest"),
    ("before", "before hash disagrees"),
    ("after", "do not match amended hashes"),
    ("parity_bytes", "parity evidence raw digest"),
    ("parity_digest", "parity evidence raw digest"),
    ("parity_missing", "parity evidence raw digest"),
    ("reason", "Missing integration change reason"),
    ("missing_change", "exactly the three allowed integration files"),
])
def test_corrupt_amendment_or_referenced_evidence_cannot_pass(original_tree, corruption, match):
    amendment = _amend(original_tree)
    if corruption == "freeze_bytes":
        # Even a metadata/whitespace-only edit breaks the raw frozen artifact digest.
        FREEZE.write_bytes(FREEZE.read_bytes() + b"\n")
    elif corruption == "freeze_digest":
        amendment["original_freeze"]["sha256"] = "0" * 64
    elif corruption == "freeze_path":
        alternate = FREEZE.with_name("same-content-different-file.json")
        alternate.write_bytes(FREEZE.read_bytes())
        amendment["original_freeze"]["path"] = alternate.as_posix()
    elif corruption in {"before", "after"}:
        amendment["code_changes"]["app/tracking/pipeline.py"][f"{corruption}_sha256_lf"] = "0" * 64
    elif corruption == "parity_bytes":
        PARITY.write_bytes(PARITY.read_bytes() + b"\n")
    elif corruption == "parity_digest":
        amendment["parity_evidence"]["sha256"] = "0" * 64
    elif corruption == "parity_missing":
        amendment["parity_evidence"]["path"] = "missing-parity.json"
    elif corruption == "reason":
        amendment["code_changes"]["app/tracking/pipeline.py"]["reason"] = " "
    elif corruption == "missing_change":
        amendment["code_changes"].pop("scripts/track_video.py")
    _write_json(DEFAULT_AMENDMENT, amendment)
    with pytest.raises(ValueError, match=match):
        verify_frozen_code(FREEZE)


def test_revalidation_detects_amendment_metadata_changes_during_export(original_tree):
    amendment = _amend(original_tree)
    first = verify_frozen_code(FREEZE)
    amendment["code_changes"]["app/tracking/pipeline.py"]["reason"] += "; updated evidence description"
    _write_json(DEFAULT_AMENDMENT, amendment)
    second = verify_frozen_code(FREEZE)
    assert second["production_code_sha256_lf"] == first["production_code_sha256_lf"]
    assert second != first  # main compares the whole provenance record before finalizing


@pytest.mark.parametrize("field", [
    "all_equal", "frozen_decision_sha256", "frozen_code_sha256_lf",
    "amended_code_sha256_lf", "added_integration_code_sha256_lf",
])
def test_correct_parity_file_digest_cannot_hide_failed_or_stale_code_evidence(original_tree, field):
    amendment = _amend(original_tree)
    result = json.loads(PARITY.read_text(encoding="utf-8"))
    if field == "all_equal":
        result[field] = False
    elif field == "frozen_decision_sha256":
        result[field] = "0" * 64
    else:
        name = next(iter(result[field]))
        result[field][name] = "0" * 64
    _write_json(PARITY, result)
    amendment["parity_evidence"]["sha256"] = digest(PARITY)
    _write_json(DEFAULT_AMENDMENT, amendment)
    with pytest.raises(ValueError, match="Parity evidence"):
        verify_frozen_code(FREEZE)


def test_added_helper_cannot_change_after_parity_was_measured(original_tree):
    _amend(original_tree)
    Path("app/tracking/anchor_state.py").write_text("changed_anchor = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Added integration code does not match"):
        verify_frozen_code(FREEZE)


def test_added_integration_map_cannot_expand_to_unreviewed_code(original_tree):
    amendment = _amend(original_tree)
    amendment["added_integration_code_sha256_lf"]["app/tracking/new_algorithm.py"] = "0" * 64
    _write_json(DEFAULT_AMENDMENT, amendment)
    with pytest.raises(ValueError, match="exactly the allowed integration helper and evidence tests"):
        verify_frozen_code(FREEZE)
