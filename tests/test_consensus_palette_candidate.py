"""Palette corroboration must retain true changes and withhold uncertain evidence."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking.identity_consensus import ConsensusTeamAssigner as PreviousAssigner
from app.tracking.pipeline import PipelineConfig, SampledObservation
from app.tracking.teams import TeamAssignment
from scripts.soccertrack_v2.candidates.identity_consensus_palette_v2 import (
    ConsensusTeamAssigner,
    palette_support,
)


@pytest.mark.parametrize('before,after,centers', [
    ([[50., 20., 30.]] * 3, [[90., 20., 30.]] * 3, [[10., 20., 30.], [90., 20., 30.]]),
    ([None] * 3, [[220., 220., 220.]] * 3, [[30., 60., 190.], [220., 220., 220.]]),
    ([[30., 60., 190.]] * 2, [[220., 220., 220.]] * 3, [[30., 60., 190.], [220., 220., 220.]]),
    ([[30., 60., 190.]] * 3, [[220., 220., 220.]] * 3, [[0., 0., 0.], [0., 0., 0.]]),
    ([[float('nan'), 60., 190.]] * 3, [[220., 220., 220.]] * 3, [[30., 60., 190.], [220., 220., 220.]]),
])
def test_ambiguous_or_missing_palette_support_is_withheld(before, after, centers):
    assert palette_support(before, after, centers) is False


def test_supported_team_change_is_independent_of_palette_slot_order():
    a, b = [[30., 60., 190.]] * 3, [[220., 220., 220.]] * 3
    for centers in [a[:1] + b[:1], b[:1] + a[:1]]:
        assert palette_support(a, b, centers)
        assert palette_support(b, a, centers)


@pytest.mark.parametrize('real_transfer', [False, True])
def test_gradual_same_palette_change_does_not_split_and_source_evidence_survives(real_transfer):
    # Rounded source colors of the old white6 failure, followed by stable white.
    colors = [[120., 163., 229.], [126., 166., 231.], [144., 177., 232.],
              [151., 184., 236.], [164., 194., 241.], [173., 201., 245.], [193., 214., 250.]]
    if real_transfer:
        colors = [[30., 60., 190.]] * 7
    colors += [[246., 246., 251.]] * 9
    outcomes = []
    for cls in [PreviousAssigner, ConsensusTeamAssigner]:
        assigner = cls()
        samples = []
        for order, color in enumerate(colors):
            box = [float(order), 0., float(order + 20), 50.]
            sample = SampledObservation(order, order * 2, order / 10, [(100, *box, .9)], None)
            assigner.observe(100, np.asarray(color))
            secondary = SimpleNamespace(tracker_id=np.array([200 if order < 7 else 201]),
                xyxy=np.array([box]), confidence=np.array([.9]))
            assigner.record_frame(sample, secondary)
            samples.append(sample)
        source = deepcopy(samples)
        assignment = TeamAssignment({100: 0}, np.array([[119.9, 149.7, 188.], [205.4, 216.8, 235.5]]), frozenset(), None)
        cfg = PipelineConfig(tracker_backend='consensus', filter_off_pitch_tracks=False)
        _, stats = assigner.refine(samples, assignment, SimpleNamespace(), cfg, 10.)
        outcomes.append(len(stats['boundaries']))
        assert all(a.persons[0][1:] == b.persons[0][1:] for a, b in zip(source, samples, strict=True))
        assert all(s.person_teams[str(s.persons[0][0])] == 0 for s in samples)
    assert outcomes == ([1, 1] if real_transfer else [1, 0])
