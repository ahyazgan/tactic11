"""Shadow refinement corrects labels while preserving original evidence and anchors."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.teams import TeamAssigner
from scripts.soccertrack_v2.benchmark_shadow_reassignment import ShadowReassignmentAssigner


def scene(refine, *, min_observations=2):
    assigner_type = ShadowReassignmentAssigner if refine else TeamAssigner
    assigner = assigner_type(min_observations=min_observations)
    for track in range(1, 8):
        for _ in range(10):
            assigner.observe(track, np.array([100., 110., 105.]) + track * .2)
    for track in range(8, 13):
        for _ in range(10):
            assigner.observe(track, np.array([200., 200., 190.]))
    return assigner


def test_shadowed_white_shirt_is_corrected_without_changing_palette():
    old, new = scene(False), scene(True)
    for assigner in (old, new):
        for color in [[120, 125, 120]] * 8 + [[205, 205, 195]] * 2:
            assigner.observe(20, np.array(color))
    before, after = old.fit(), new.fit()
    assert before.team_by_track[20] == before.team_by_track[1]
    assert after.team_by_track[20] == after.team_by_track[8]
    assert after.team_by_track[20] != before.team_by_track[20]
    assert new.shadow_reassigned_tracks == frozenset({20})
    np.testing.assert_array_equal(after.centers, before.centers)
    assert after.outlier_tracks == before.outlier_tracks


def test_bright_outlier_cannot_remove_a_valid_player_or_rescue_rejected_track():
    old, new = scene(False), scene(True)
    for assigner in (old, new):
        for color in [[200, 200, 190]] * 8 + [[255, 255, 255]] * 2:
            assigner.observe(20, np.array(color))
        for color in [[10, 10, 10]] * 8 + [[205, 205, 195]] * 2:
            assigner.observe(21, np.array(color))
    before, after = old.fit(), new.fit()
    assert before.team_by_track[20] is not None
    assert after.team_by_track[20] == before.team_by_track[20]
    assert before.team_by_track[21] is None
    assert after.team_by_track[21] is None
    assert after.outlier_tracks == before.outlier_tracks


def test_refinement_respects_configured_evidence_and_eligible_tracks():
    assigner = scene(True, min_observations=5)
    for color in [[120, 125, 120]] * 8 + [[205, 205, 195]] * 4:
        assigner.observe(20, np.array(color))
    assigner.observe(21, np.array([205, 205, 195]))
    result = assigner.fit(eligible_tracks=set(range(1, 14)) | {21})
    assert result.team_by_track[20] is result.team_by_track[21] is None
    assert not assigner.shadow_reassigned_tracks
    assert assigner.fit().team_by_track[20] == assigner.fit().team_by_track[8]


@pytest.mark.parametrize("colors", [[], [[120, 120, 120]] * 8])
def test_invalid_initial_palette_stays_unassigned(colors):
    assigner = ShadowReassignmentAssigner(min_observations=1)
    for track, color in enumerate(colors):
        assigner.observe(track, np.array(color))
    result = assigner.fit()
    assert all(team is None for team in result.team_by_track.values())
    assert not result.centers.any()
    assert not assigner.shadow_reassigned_tracks


def test_supplied_anchor_is_not_mutated_and_repeat_fit_is_stable():
    assigner = scene(True)
    for color in [[120, 125, 120]] * 8 + [[205, 205, 195]] * 2:
        assigner.observe(20, np.array(color))
    anchor = np.array([[200., 200., 190.], [100., 110., 105.]])
    before = anchor.copy()
    first, second = assigner.fit(anchor), assigner.fit(anchor)
    assert first.team_by_track[20] == 0
    assert first.team_by_track == second.team_by_track
    np.testing.assert_array_equal(anchor, before)
