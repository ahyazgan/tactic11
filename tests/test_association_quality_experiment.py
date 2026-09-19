"""Assignment invariants and known-development regressions, not blind accuracy."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from scripts.soccertrack_v2.association_quality_experiment import (
    constrained_assignment,
    quality_associate,
)


def test_forbidden_assignment_cannot_steal_a_legal_match():
    pytest.importorskip("scipy")
    utility = np.array([[.9, .8], [.85, .99]])
    eligible = np.array([[True, True], [True, False]])
    matches, unmatched_d, unmatched_t = constrained_assignment(utility, eligible)
    assert matches.tolist() == [[0, 1], [1, 0]]
    assert not len(unmatched_d) and not len(unmatched_t)


def test_legal_negative_scores_remain_eligible_and_arrays_are_unchanged():
    pytest.importorskip("scipy")
    utility = np.array([[-8., -9.], [-10., -20.]])
    before = utility.copy()
    matches, _, _ = constrained_assignment(utility, np.ones((2, 2), dtype=bool))
    assert matches.tolist() == [[0, 1], [1, 0]]
    np.testing.assert_array_equal(utility, before)


@pytest.mark.parametrize("shape", [(0, 0), (0, 2), (3, 0), (2, 3)])
def test_empty_or_forbidden_candidates_stay_unmatched(shape):
    pytest.importorskip("scipy")
    matches, detections, tracks = constrained_assignment(np.zeros(shape), np.zeros(shape, dtype=bool))
    assert matches.shape == (0, 2)
    assert detections.tolist() == list(range(shape[0]))
    assert tracks.tolist() == list(range(shape[1]))


def associate(det, tracks, mode="shape_guard"):
    pytest.importorskip("scipy")
    det, tracks = np.asarray(det, dtype=float), np.asarray(tracks, dtype=float)
    return quality_associate(det, tracks, np.ones((len(det), 1)), np.ones((len(tracks), 1)),
        .3, np.zeros((len(tracks), 2)), tracks.copy(), .2, .75, True, .5, True, True, mode=mode)


def test_two_overlapping_real_bodies_keep_two_assignments():
    boxes = [[0, 0, 20, 50, .9], [10, 0, 30, 50, .9]]
    matches, detections, tracks = associate(boxes, boxes)
    assert matches.tolist() == [[0, 0], [1, 1]]
    assert not len(detections) and not len(tracks)


def test_lower_body_candidate_is_unmatched_when_a_body_supports_the_old_track():
    matches, detections, tracks = associate(
        [[2, 1, 22, 48, .8], [1, 30, 22, 51, .9]], [[0, 0, 20, 50, .8]])
    assert matches.tolist() == [[0, 0]]
    assert detections.tolist() == [1]  # Available for a separate track, never deleted.
    assert not len(tracks)


def test_lone_short_body_is_not_rejected_as_a_duplicate():
    matches, detections, tracks = associate([[0, 20, 20, 50, .8]], [[0, 0, 20, 50, .8]])
    assert matches.tolist() == [[0, 0]]
    assert not len(detections) and not len(tracks)


@pytest.mark.parametrize("name", ["white_turn", "blue_referee"])
def test_known_relations_are_preserved_without_oracle_box_removal(name):
    pytest.importorskip("supervision")
    pytest.importorskip("filterpy")
    from app.tracking._vendor.deepocsort import ocsort
    from scripts.soccertrack_v2.audit_identity_failures import FIXTURES, load_fixture, replay_case

    source = load_fixture(FIXTURES / f"{name}.json.gz")
    before = deepcopy(source)
    with patch.object(ocsort, "associate", side_effect=lambda *a: quality_associate(*a, mode="shape_guard")):
        result = replay_case(source)
    assert result["linked"]
    assert not result["oracle_fragment_removed"]
    assert source == before
    samples = {s["frame_idx"]: {r["raw_index"]: r["box"] for r in s["detections"]}
               for s in source["samples"]}
    for frame in result["frames"]:
        ids = [row["track_id"] for row in frame["observations"]]
        assert len(ids) == len(set(ids))
        for row in frame["observations"]:
            assert row["box"] == samples[frame["frame_idx"]][row["raw_index"]]
