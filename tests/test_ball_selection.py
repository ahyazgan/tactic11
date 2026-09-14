import numpy as np
import pytest

from scripts.soccertrack_v2.ball_selection_experiment import (
    preferred_index,
    select_ball_index,
    yellow_fraction,
)


def test_default_selection_preserves_confidence_and_yellow_preference_is_explicit():
    rgb = np.full((10, 20, 3), 220, dtype=np.uint8)
    rgb[:, 10:] = [230, 230, 50]
    boxes = [[0, 0, 10, 10], [10, 0, 20, 10]]
    confidence = [.9, .6]
    assert select_ball_index(rgb, boxes, confidence) == 0
    assert select_ball_index(rgb, boxes, confidence, "yellow") == 1


def test_no_yellow_evidence_falls_back_and_empty_candidates_do_not_create_ball():
    assert preferred_index([.9, .5], [0, 0]) == 0
    assert preferred_index([], []) is None
    assert yellow_fraction(np.zeros((2, 2, 3), dtype=np.uint8), [4, 4, 6, 6]) == 0
    assert yellow_fraction(np.full((20, 20, 3), [230, 230, 50], dtype=np.uint8), [-10, -10, -4, -4]) == 0


def test_white_snow_dark_grass_and_green_are_not_yellow():
    for colour in ([250, 250, 250], [30, 40, 20], [60, 220, 50]):
        assert yellow_fraction(np.full((4, 4, 3), colour, dtype=np.uint8), [0, 0, 4, 4]) == 0


def test_invalid_candidate_score_lengths_and_unknown_policy_fail():
    with pytest.raises(ValueError):
        preferred_index([.5, .9], [.2])
    with pytest.raises(ValueError):
        select_ball_index(np.zeros((2, 2, 3)), [], [], "guess")
