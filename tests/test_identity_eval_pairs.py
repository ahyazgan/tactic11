"""Small adversarial fixtures for the sparse identity-pair evaluator."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.soccertrack_v2.identity_eval_pairs import evaluate


def fixture():
    labels = {"observations": [
        {"id": "a0", "segment": 0, "frame_idx": 0, "bbox": [0, 0, 10, 20]},
        {"id": "b0", "segment": 0, "frame_idx": 0, "bbox": [20, 0, 30, 20]},
        {"id": "a1", "segment": 0, "frame_idx": 2, "bbox": [1, 0, 11, 20]},
        {"id": "b1", "segment": 0, "frame_idx": 2, "bbox": [21, 0, 31, 20]},
    ], "pairs": [
        {"left": "a0", "right": "a1", "relation": "same"},
        {"left": "b0", "right": "b1", "relation": "same"},
        {"left": "a0", "right": "b1", "relation": "different"},
    ]}
    payload = {0: {"samples": [
        {"frame_idx": 0, "persons": [[1, 0, 0, 10, 20, .9], [2, 20, 0, 30, 20, .9]]},
        {"frame_idx": 2, "persons": [[1, 1, 0, 11, 20, .9], [2, 21, 0, 31, 20, .9]]},
    ]}}
    return labels, payload


def test_correct_and_swapped_identities():
    labels, payload = fixture()
    result = evaluate(labels, payload)
    assert result["same_person_recall"] == result["different_person_separation"] == 1
    payload[0]["samples"][1]["persons"][0][0] = 2
    payload[0]["samples"][1]["persons"][1][0] = 1
    result = evaluate(labels, payload)
    assert result["same_person_recall"] == result["different_person_separation"] == 0
    assert result["counts"]["false_split"] == 2
    assert result["counts"]["false_join"] == 1


def test_fragmentation_loses_recall_and_deletion_cannot_improve_score():
    labels, payload = fixture()
    payload[0]["samples"][1]["persons"][0][0] = 3
    result = evaluate(labels, payload)
    assert result["same_person_recall"] == .5
    payload[0]["samples"][1]["persons"].clear()
    result = evaluate(labels, payload)
    assert result["same_person_recall"] == result["different_person_separation"] == 0
    assert result["covered_observations"] == 2
    assert result["counts"]["same_uncovered"] == 2


def test_identity_is_scoped_by_camera_continuity_and_segment():
    labels, payload = fixture()
    payload[0]["samples"][1]["continuity_id"] = 1
    assert evaluate(labels, payload)["same_person_recall"] == 0
    other = deepcopy(payload[0]["samples"][1])
    other["continuity_id"] = 0
    payload[3] = {"samples": [other]}
    for obs in labels["observations"][2:]:
        obs["segment"] = 3
    assert evaluate(labels, payload)["same_person_recall"] == 0


def test_ambiguous_boxes_and_unknown_relations_are_not_scored_as_correct():
    labels, payload = fixture()
    payload[0]["samples"][1]["persons"].append([3, 1, 0, 11, 20, .9])
    result = evaluate(labels, payload)
    assert result["ambiguous_observations"] == 1
    assert result["same_person_recall"] == .5
    labels["pairs"][0]["relation"] = "uncertain"
    result = evaluate(labels, payload)
    assert result["same_person_recall"] == 1
    assert result["counts"]["uncertain_excluded"] == 1


def test_duplicate_or_invalid_labels_fail_loudly():
    labels, payload = fixture()
    labels["pairs"].append(dict(labels["pairs"][0]))
    with pytest.raises(ValueError, match="duplicate pair"):
        evaluate(labels, payload)
    labels, payload = fixture()
    labels["observations"][0]["bbox"] = [0, 0, float("nan"), 10]
    with pytest.raises(ValueError, match="invalid box"):
        evaluate(labels, payload)
