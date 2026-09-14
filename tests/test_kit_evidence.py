"""Separate shirt observations must retain uncertainty and official colours."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from app.tracking.kit_evidence import extract_kit_evidence, fit_kit_evidence
from app.tracking.teams import TeamAssigner, torso_color


def palette_observations():
    bright = {t: [[20, 70, 150]] * 4 for t in range(5)}
    bright.update({t: [[240, 245, 245]] * 4 for t in range(5, 10)})
    broad = {t: [[10, 35, 75]] * 4 for t in range(5)}
    broad.update({t: [[180, 180, 180]] * 4 for t in range(5, 10)})
    return bright, broad


def fixture_frame():
    frame = np.full((12, 10, 3), [20, 150, 20], dtype=np.uint8)
    k = np.arange(30)
    frame[1:6, 2:8] = np.column_stack((k, 2 * k, 3 * k + 10)).reshape(5, 6, 3)
    return frame


@pytest.mark.parametrize("box", [(0, 0, 10, 12), (-2, -1, 10, 12)])
def test_known_pixels_keep_exact_frozen_features_and_existing_broad_colour(box):
    frame = fixture_frame()
    before = frame.copy()
    evidence = extract_kit_evidence(frame, box)
    assert evidence is not None
    np.testing.assert_array_equal(evidence.bright, [26.5, 53., 89.5])
    np.testing.assert_array_equal(evidence.broad, [23.5, 47., 80.5])
    np.testing.assert_array_equal(evidence.appearance, [18., 36., 64.])
    np.testing.assert_array_equal(evidence.broad, torso_color(frame, box))
    np.testing.assert_array_equal(frame, before)


def test_bright_grass_does_not_replace_the_detected_shirt_colour():
    frame = np.full((12, 10, 3), [20, 250, 20], dtype=np.uint8)
    frame[1, 2:8] = [40, 70, 130]
    evidence = extract_kit_evidence(frame, (0, 0, 10, 12))
    assert evidence is not None
    for feature in (evidence.bright, evidence.broad, evidence.appearance):
        np.testing.assert_array_equal(feature, [40, 70, 130])


@pytest.mark.parametrize("color", [[0, 0, 0], [20, 100, 20]])
def test_dark_or_all_grass_crop_has_finite_evidence_but_does_not_invent_two_teams(color):
    frame = np.full((12, 10, 3), color, dtype=np.uint8)
    evidence = extract_kit_evidence(frame, (0, 0, 10, 12))
    assert evidence is not None
    for feature in (evidence.bright, evidence.broad, evidence.appearance):
        np.testing.assert_array_equal(feature, color)
    result = fit_kit_evidence({0: [evidence.bright] * 2, 1: [evidence.bright] * 2},
                             {0: [evidence.broad] * 2, 1: [evidence.broad] * 2})
    assert result.team_by_track == {0: None, 1: None}
    assert result.outlier_tracks == {0, 1}
    assert np.isfinite(result.centers).all()


@pytest.mark.parametrize("box", [(-20, 0, -10, 12), (20, 0, 30, 12), (0, -20, 10, -10),
                                  (0, 20, 10, 30), (0, 0, 1, 3), (10, 10, 1, 1),
                                  (0, 0, np.inf, 12), (0, np.nan, 10, 12)])
def test_missing_or_invalid_box_never_wraps_to_unrelated_pixels(box):
    assert extract_kit_evidence(fixture_frame(), box) is None


def test_nonfinite_source_pixels_are_missing_evidence():
    frame = fixture_frame().astype(float)
    frame[2, 3] = np.nan
    assert extract_kit_evidence(frame, (0, 0, 10, 12)) is None


def test_broader_shirt_colour_vetoes_an_official_hidden_by_a_bright_patch():
    bright, broad = palette_observations()
    bright[10] = [[235, 235, 220]] * 4
    broad[10] = [[180, 160, 20]] * 4
    bright_only = TeamAssigner()
    for track, observations in bright.items():
        for color in observations:
            bright_only.observe(track, np.asarray(color))
    assert bright_only.fit().team_by_track[10] is not None
    result = fit_kit_evidence(bright, broad)
    assert result.team_by_track[10] is None
    assert result.team_by_track[0] != result.team_by_track[5]
    assert all(result.team_by_track[t] is not None for t in range(10))


def test_broad_brightness_distance_cannot_veto_a_matching_shirt_tint():
    bright, broad = palette_observations()
    bright[10], broad[10] = [[240, 245, 245]] * 4, [[140, 140, 140]] * 4
    broad_only = TeamAssigner()
    for track, observations in broad.items():
        for color in observations:
            broad_only.observe(track, np.asarray(color))
    assert broad_only.fit().team_by_track[10] is None
    result = fit_kit_evidence(bright, broad)
    assert result.team_by_track[10] == result.team_by_track[5]
    assert result.team_by_track[10] is not None


@pytest.mark.parametrize("missing", [[], [[180, 180, 180]]])
def test_a_track_needs_both_independent_histories_even_with_a_clear_bright_colour(missing):
    bright, broad = palette_observations()
    broad[9] = missing
    result = fit_kit_evidence(bright, broad)
    assert result.team_by_track[9] is None
    assert all(result.team_by_track[t] is not None for t in range(9))


@pytest.mark.parametrize("ambiguous_branch", ["bright", "broad"])
def test_two_colours_in_one_branch_cannot_overrule_an_ambiguous_other_branch(ambiguous_branch):
    bright, broad = palette_observations()
    ambiguous = bright if ambiguous_branch == "bright" else broad
    for track in ambiguous:
        ambiguous[track] = [[80, 80, 80]] * 4
    result = fit_kit_evidence(bright, broad)
    assert all(team is None for team in result.team_by_track.values())
    assert np.isfinite(result.centers).all()


def test_filtered_tracks_cannot_change_the_two_palettes_or_existing_assignments():
    bright, broad = palette_observations()
    expected = fit_kit_evidence(bright, broad)
    for track in range(10, 40):
        bright[track] = [[220, 20, 180]] * 8
        broad[track] = [[120, 10, 100]] * 8
    actual = fit_kit_evidence(bright, broad, eligible_tracks=set(range(10)))
    np.testing.assert_array_equal(actual.centers, expected.centers)
    assert {t: actual.team_by_track[t] for t in range(10)} == expected.team_by_track
    assert all(actual.team_by_track[t] is None for t in range(10, 40))


def test_absent_and_nonfinite_observations_remain_unknown_without_contaminating_palettes():
    bright, broad = palette_observations()
    expected = fit_kit_evidence(bright, broad)
    bright[10] = [None, [np.nan, 1, 2], [1, 2]]
    broad[10] = [None]
    before = deepcopy(broad)
    actual = fit_kit_evidence(bright, broad)
    np.testing.assert_array_equal(actual.centers, expected.centers)
    assert actual.team_by_track[10] is None
    assert broad == before
    assert fit_kit_evidence({}, {}).team_by_track == {}


def test_anchor_reorders_anonymous_teams_without_changing_the_official_veto():
    bright, broad = palette_observations()
    bright[10], broad[10] = [[235, 235, 220]] * 4, [[180, 160, 20]] * 4
    first = fit_kit_evidence(bright, broad)
    second = fit_kit_evidence(bright, broad, first.centers[::-1])
    for track in range(10):
        assert second.team_by_track[track] == 1 - first.team_by_track[track]
    assert first.team_by_track[10] is second.team_by_track[10] is None
