"""Identity handoffs, ambiguous appearance and camera-epoch isolation."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.identity_split import IdentityObservation, appearance_phases, split_identities

BLUE = np.array([40., 70., 160.])
WHITE = np.array([215., 220., 235.])


def phases(colors, **kwargs):
    return appearance_phases(colors, seconds=np.arange(len(colors)) * .08,
                             max_gap_seconds=.12, **kwargs)


def test_confirmed_opponent_handoff_is_backdated_without_losing_rows():
    output, boundaries = phases([BLUE] * 10 + [WHITE] * 6)
    assert output == [0] * 10 + [1] * 6
    assert len(boundaries) == 1
    assert (boundaries[0].first_index, boundaries[0].confirmed_index) == (10, 12)


def test_short_occluding_color_does_not_split_identity():
    output, boundaries = phases([BLUE] * 10 + [WHITE] * 2 + [BLUE] * 10)
    assert output == [0] * 22
    assert boundaries == []


def test_pure_shade_change_cannot_prove_an_opponent_handoff():
    output, boundaries = phases([BLUE] * 10 + [BLUE * .3] * 10)
    assert output == [0] * 20
    assert boundaries == []


@pytest.mark.parametrize("missing", [None, np.array([np.nan, 2, 3]), np.array([2, 3]),
                                    np.array([-1, 2, 3])])
def test_missing_or_invalid_color_interrupts_confirmation(missing):
    output, boundaries = phases([BLUE] * 10 + [WHITE, missing, WHITE, WHITE])
    assert output == [0] * 14
    assert boundaries == []


def test_detection_gap_interrupts_confirmation_but_keeps_prior_evidence():
    colors = [BLUE] * 10 + [WHITE] * 4
    seconds = [i * .08 for i in range(11)] + [1.5, 1.58, 1.66]
    output, boundaries = appearance_phases(colors, seconds=seconds, max_gap_seconds=.12)
    assert output == [0] * 11 + [1] * 3
    assert (boundaries[0].first_index, boundaries[0].confirmed_index) == (11, 13)


def test_fewer_than_five_prior_observations_cannot_prove_handoff():
    output, boundaries = phases([BLUE] * 4 + [WHITE] * 3)
    assert output == [0] * 7
    assert boundaries == []


def test_auxiliary_cue_requires_recent_collision_and_broad_contradiction():
    raw_a, raw_b = np.array([130., 150., 200.]), np.array([172., 171., 215.])
    raw = [raw_a] * 10 + [raw_b] * 3
    auxiliary = [BLUE] * 10 + [WHITE] * 3
    no_overlap, _ = phases(raw, auxiliary_colors=auxiliary, collision_mask=[False] * 13)
    old_overlap, _ = phases(raw, auxiliary_colors=auxiliary, collision_mask=[True] + [False] * 12)
    recent = [False] * 9 + [True] + [False] * 3
    overlap, boundaries = phases(raw, auxiliary_colors=auxiliary, collision_mask=recent)
    unchanged, _ = phases([raw_a] * 13, auxiliary_colors=auxiliary, collision_mask=recent)
    assert no_overlap == old_overlap == unchanged == [0] * 13
    assert overlap == [0] * 10 + [1] * 3
    assert boundaries[0].source == "collision_appearance"


def test_auxiliary_feature_cannot_bridge_missing_broad_torso_evidence():
    raw_a, raw_b = np.array([130., 150., 200.]), np.array([172., 171., 215.])
    output, boundaries = phases(
        [raw_a] * 10 + [raw_b, None, raw_b],
        auxiliary_colors=[BLUE] * 10 + [WHITE] * 3,
        collision_mask=[False] * 9 + [True] + [False] * 3,
    )
    assert output == [0] * 13
    assert boundaries == []


def test_multiple_changes_allocate_successive_local_phases():
    output, boundaries = phases([BLUE] * 10 + [WHITE] * 10 + [BLUE] * 5)
    assert output == [0] * 10 + [1] * 10 + [2] * 5
    assert [b.phase for b in boundaries] == [1, 2]


def test_wrapper_preserves_input_alignment_and_isolates_raw_ids_and_camera_cuts():
    rows = []
    for order in range(13):
        rows.append(IdentityObservation(0, 1, order, order * .08, BLUE if order < 10 else WHITE))
        rows.append(IdentityObservation(0, 2, order, order * .08, WHITE))
    rows.extend(IdentityObservation(1, 1, order, order * .08, BLUE) for order in range(5))
    result = split_identities(rows, max_gap_seconds=.12)
    first_track = result.observation_ids[:26:2]
    second_track = result.observation_ids[1:26:2]
    after_cut = result.observation_ids[26:]
    assert first_track[:10] == (1,) * 10
    assert len(set(first_track[10:])) == 1 and first_track[10] != 1
    assert second_track == (2,) * 13
    assert len(set(after_cut)) == 1 and after_cut[0] not in result.observation_ids[:26]
    assert len(result.observation_ids) == len(rows)
    assert result.boundaries[0].first_order == 10
    assert result.boundaries[0].confirmed_order == 12


def test_same_color_players_never_join_and_no_state_leaks_between_calls():
    rows = [IdentityObservation(0, tid, 0, 0, BLUE) for tid in (4, 7)]
    assert split_identities(rows, max_gap_seconds=.12).observation_ids == (4, 7)
    assert split_identities(rows, max_gap_seconds=.12).observation_ids == (4, 7)


def test_duplicate_or_reversed_track_observations_are_rejected():
    row = IdentityObservation(0, 1, 1, .08, BLUE)
    with pytest.raises(ValueError, match="duplicate"):
        split_identities([row, row], max_gap_seconds=.12)
    earlier = IdentityObservation(0, 1, 0, 0, BLUE)
    with pytest.raises(ValueError, match="ordered"):
        split_identities([row, earlier], max_gap_seconds=.12)


def test_invalid_time_or_auxiliary_alignment_is_rejected():
    with pytest.raises(ValueError, match="ordered"):
        appearance_phases([BLUE, BLUE], seconds=[.08, 0], max_gap_seconds=.12)
    with pytest.raises(ValueError, match="ordered"):
        appearance_phases([BLUE], seconds=[np.nan], max_gap_seconds=.12)
    with pytest.raises(ValueError, match="aligned auxiliary"):
        phases([BLUE], auxiliary_colors=[BLUE], collision_mask=[])
    with pytest.raises(ValueError, match="positive thresholds"):
        appearance_phases([BLUE], seconds=[0], max_gap_seconds=0)


def test_empty_input_has_no_invented_identity():
    result = split_identities([], max_gap_seconds=.12)
    assert result.observation_ids == result.boundaries == ()
