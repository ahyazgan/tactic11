import numpy as np

from scripts.soccertrack_v2.excess_markers import classify

TRUTH = np.array([[50.0, 34.0], [20.0, 10.0]])


def test_marker_on_clamped_line_is_clamped_even_when_near_a_player():
    assert classify(np.array([0.0, 30.0]), np.array([[0.5, 30.0]]), set()) == "clamped"
    assert classify(np.array([60.0, 68.0]), TRUTH, set()) == "clamped"


def test_marker_next_to_matched_player_is_duplicate_and_next_to_free_player_is_near_miss():
    assert classify(np.array([51.0, 34.0]), TRUTH, {0}) == "duplicate"
    assert classify(np.array([24.0, 10.0]), TRUTH, {0}) == "near_miss"


def test_lone_marker_is_split_by_distance_to_line():
    assert classify(np.array([80.0, 2.0]), TRUTH, {0, 1}) == "alone_line"
    assert classify(np.array([80.0, 40.0]), TRUTH, {0, 1}) == "alone_inside"
