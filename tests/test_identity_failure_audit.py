"""Known-error characterization and causal interventions, not accuracy approval."""
from __future__ import annotations

import gzip
import json
from copy import deepcopy

import pytest

from scripts.soccertrack_v2.audit_identity_failures import (
    CASES,
    FIXTURES,
    digest,
    load_fixture,
    replay_case,
)


@pytest.fixture(params=CASES)
def source(request):
    return load_fixture(FIXTURES / f"{request.param}.json.gz")


@pytest.fixture(scope="module")
def outcomes():
    pytest.importorskip("supervision")
    pytest.importorskip("filterpy")
    return {name: {label: replay_case(load_fixture(FIXTURES / f"{name}.json.gz"),
                                    iou=iou, remove_fragment=remove)
                  for label, iou, remove in [("original", .3, False), ("iou_02", .2, False),
                                             ("oracle", .3, True), ("both", .2, True)]}
            for name in CASES}


def test_fixture_has_full_warmup_and_independent_source_annotations(source):
    assert source["samples"][0]["frame_idx"] == 0
    assert len(source["source_sha256"]) == 3
    assert source["fragment"]["raw_index"] != source["support"]["raw_index"]
    assert source["endpoints"][0]["id"] != source["endpoints"][1]["id"]
    assert source["endpoints"][0]["frame_idx"] < source["fragment"]["frame_idx"] < source["endpoints"][1]["frame_idx"]


def test_fixture_bytes_match_the_recorded_audit(source):
    from pathlib import Path

    report = json.loads(Path("docs/measurements/identity-failure-audit-results.json").read_text(encoding="utf-8"))
    path = FIXTURES / f"{source['name']}.json.gz"
    # The report was created on Windows; compare normalized path spelling.
    hashes = {name.replace("\\", "/"): value for name, value in report["fixture_sha256"].items()}
    assert digest(path) == hashes[path.as_posix()]


def test_original_and_lower_threshold_still_fail_both_known_relations(outcomes):
    # This records the unresolved errors; it is not a test claiming a fix.
    for case in outcomes.values():
        for arm in ("original", "iou_02"):
            assert not case[arm]["linked"]
            assert None not in case[arm]["endpoint_ids"].values()


def test_white_turn_full_body_is_rejected_before_appearance_can_help(outcomes):
    row = next(r for r in outcomes["white_turn"]["original"]["first_stage"] if r["frame_idx"] == 298)
    by_index = {r["raw_index"]: r for r in row["candidates"]}
    assert .2 < by_index[17]["iou"] < .3
    assert not by_index[17]["geometrically_eligible"]
    assert by_index[18]["assigned_track_id"] == row["target_id"]
    assert not outcomes["white_turn"]["oracle"]["linked"]
    assert outcomes["white_turn"]["both"]["linked"]


def test_blue_body_and_fragment_compete_for_distinct_existing_tracks(outcomes):
    row = next(r for r in outcomes["blue_referee"]["original"]["first_stage"] if r["frame_idx"] == 458)
    by_index = {r["raw_index"]: r for r in row["candidates"]}
    assert by_index[14]["geometrically_eligible"]
    assert by_index[24]["geometrically_eligible"]
    assert by_index[24]["assigned_track_id"] == row["target_id"]
    assert by_index[14]["assigned_track_id"] != row["target_id"]
    assert outcomes["blue_referee"]["oracle"]["linked"]


def test_oracle_cannot_mutate_inputs_or_invent_boxes(source):
    pytest.importorskip("supervision")
    pytest.importorskip("filterpy")
    original = deepcopy(source)
    result = replay_case(source, remove_fragment=True)
    assert source == original
    samples = {r["frame_idx"]: r for r in source["samples"]}
    for frame in result["frames"]:
        source_rows = {r["raw_index"]: r for r in samples[frame["frame_idx"]]["detections"]}
        for row in frame["observations"]:
            assert row["box"] == source_rows[row["raw_index"]]["box"]
            assert not (frame["frame_idx"] == source["fragment"]["frame_idx"]
                        and row["raw_index"] == source["fragment"]["raw_index"])


@pytest.mark.parametrize("corruption", ["warmup", "frame", "index", "annotation"])
def test_corrupt_provenance_or_warmup_is_rejected(source, tmp_path, corruption):
    if corruption == "warmup":
        source["samples"] = source["samples"][1:]
    elif corruption == "frame":
        source["samples"][1]["frame_idx"] += 1
    elif corruption == "index":
        sample = source["samples"][0]
        sample["detections"].append(deepcopy(sample["detections"][0]))
    else:
        source["endpoints"][0]["box"][0] += 1
    path = tmp_path / "fixture.json.gz"
    path.write_bytes(gzip.compress(json.dumps(source).encode(), mtime=0))
    with pytest.raises(ValueError):
        load_fixture(path)
