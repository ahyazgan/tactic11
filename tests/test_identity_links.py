"""Fragment links must satisfy motion in both directions and component safety."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from app.tracking.identity_links import LinkObservation, link_identities

BLUE = np.array([80., 120., 190.])


def track(tid, start, x, *, velocity=20., team=0, continuity=0, collision=False):
    rows = []
    for index in range(3):
        seconds = start + .08 * index
        center = x + velocity * .08 * index
        rows.append(LinkObservation(
            tid, continuity, round(seconds * 100), seconds,
            (center - 10, 0., center + 10, 40.), BLUE.copy(),
            (center / 25, 0.), team, collision,
        ))
    return rows


def ordered(*groups):
    return sorted([row for group in groups for row in group], key=lambda row: (row.seconds, row.track_id))


def test_consistent_bidirectional_motion_links_without_changing_boxes_or_teams():
    first = track(1, 0, 0)
    second = track(2, .4, 8)
    rows = ordered(first, second)
    result = link_identities(rows)
    assert result.observation_ids == (1,) * 6
    assert len(result.links) == 1
    assert result.links[0].forward_residual < 1e-10
    assert result.links[0].backward_residual < 1e-10
    assert [row.team for row in rows] == [0] * 6
    assert second[0].bbox == (-2., 0., 18., 40.)
    np.testing.assert_array_equal(rows[0].color, BLUE)


def test_one_good_prediction_cannot_hide_incompatible_reverse_motion():
    first = track(1, 0, 0, velocity=80)
    # Forward prediction is exact, but backward/stationary distance is one
    # body height: the unsafe minimum-residual rule accepted this situation.
    second = track(2, .66, 52.8, velocity=0)
    result = link_identities(ordered(first, second))
    assert result.links == ()
    assert set(result.observation_ids) == {1, 2}


def test_opposed_motion_rejects_close_crossing_players():
    first = track(1, 0, 0, velocity=20)
    second = track(2, .24, 4.8, velocity=-20)
    result = link_identities(ordered(first, second))
    assert result.links == ()


@pytest.mark.parametrize("which", ["source_end", "target_start"])
def test_overlap_at_candidate_endpoint_prevents_link(which):
    first, second = track(1, 0, 0), track(2, .4, 8)
    if which == "source_end":
        first[-1] = replace(first[-1], collision=True)
    else:
        second[0] = replace(second[0], collision=True)
    assert link_identities(ordered(first, second)).links == ()


def test_collision_at_unrelated_far_endpoint_does_not_block_clear_link():
    first, second = track(1, 0, 0), track(2, .4, 8)
    first[0] = replace(first[0], collision=True)
    second[-1] = replace(second[-1], collision=True)
    assert len(link_identities(ordered(first, second)).links) == 1


def test_ambiguous_equal_successors_are_not_arbitrarily_joined():
    first = track(1, 0, 0)
    second, third = track(2, .4, 7.5), track(3, .4, 8.5)
    result = link_identities(ordered(first, second, third))
    assert result.links == ()


def test_split_cannot_link_constraint_survives_transitive_components():
    first, middle, last = track(1, 0, 0), track(2, .24, 4.8, team=None), track(3, .48, 9.6)
    rows = ordered(first, middle, last)
    result = link_identities(rows, cannot_link={(1, 3)}, ambiguity_margin=0)
    by_source = {row.track_id: identity for row, identity in zip(rows, result.observation_ids, strict=True)}
    assert by_source[1] == by_source[2]
    assert by_source[1] != by_source[3]
    assert len(result.links) == 1


def test_unknown_team_fragment_cannot_bridge_opponent_components():
    first = track(1, 0, 0, team=0)
    middle = track(2, .24, 4.8, team=None)
    last = track(3, .48, 9.6, team=1)
    rows = ordered(first, middle, last)
    result = link_identities(rows, ambiguity_margin=0)
    by_source = {row.track_id: identity for row, identity in zip(rows, result.observation_ids, strict=True)}
    assert by_source[1] != by_source[3]
    assert len(result.links) == 1
    assert all(row.team is None for row in rows if row.track_id == 2)


@pytest.mark.parametrize("change", ["camera", "team", "color", "gap", "pitch", "missing_color", "negative_color"])
def test_missing_or_conflicting_evidence_does_not_join(change):
    first, second = track(1, 0, 0), track(2, .4, 8)
    if change == "camera":
        second = [replace(row, continuity_id=1) for row in second]
    elif change == "team":
        second = [replace(row, team=1) for row in second]
    elif change == "color":
        second = [replace(row, color=np.array([240., 220., 20.])) for row in second]
    elif change == "gap":
        second = track(2, 2, 40)
    elif change == "pitch":
        second = [replace(row, pitch_position=None) for row in second]
    elif change == "negative_color":
        second = [replace(row, color=np.array([-1., 120., 190.])) for row in second]
    else:
        second = [replace(row, color=None) for row in second]
    assert link_identities(ordered(first, second)).links == ()


def test_concurrent_same_kit_tracks_keep_distinct_ids():
    rows = ordered(track(1, 0, 0), track(2, 0, 1))
    result = link_identities(rows)
    assert result.links == ()
    assert set(result.observation_ids) == {1, 2}


def test_reused_numeric_track_id_after_camera_cut_stays_a_new_identity():
    before, after = track(1, 0, 0), track(1, .4, 8, continuity=1)
    result = link_identities(ordered(before, after))
    assert result.observation_ids[:3] == (1, 1, 1)
    assert len(set(result.observation_ids[3:])) == 1
    assert result.observation_ids[3] != 1
    assert result.links == ()


def test_short_fragments_cannot_supply_motion_estimates():
    assert link_identities(ordered(track(1, 0, 0)[:2], track(2, .4, 8))).links == ()


def test_no_palette_refit_or_global_state(monkeypatch):
    from app.tracking.teams import TeamAssigner

    def forbidden(*args, **kwargs):
        pytest.fail("identity linking must not refit team assignment")

    monkeypatch.setattr(TeamAssigner, "fit", forbidden)
    rows = ordered(track(1, 0, 0), track(2, .4, 8))
    assert link_identities(rows) == link_identities(rows)


def test_invalid_observations_are_rejected_and_empty_input_is_safe():
    rows = track(1, 0, 0)
    with pytest.raises(ValueError, match="duplicate"):
        link_identities([rows[0], rows[0]])
    with pytest.raises(ValueError, match="ordered"):
        link_identities(rows[::-1])
    with pytest.raises(ValueError, match="positive-area"):
        link_identities([replace(rows[0], bbox=(0., 0., 0., 1.))])
    with pytest.raises(ValueError, match="positive gap"):
        link_identities([], max_gap_seconds=0)
    assert link_identities([]).observation_ids == ()
