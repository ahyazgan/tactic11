"""Independent evidence must agree before a baseline identity is partitioned."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from scripts.soccertrack_v2.color_consensus_experiment import transform


def example(*, motion_change=True, brightness_only=False, missing=False):
    raw = {"stats": {"effective_track_fps": 10.}, "samples": [], "detected_persons": {}}
    candidate, support = {"samples": []}, {"samples": []}
    for order in range(16):
        box = [float(order), 0., float(order + 20), 50.]
        color = [30., 60., 190.] if order < 8 else ([15., 30., 95.] if brightness_only else [220., 220., 220.])
        sample = dict(order=order, frame_idx=order * 2, seconds=order / 10,
                      persons=[[100, *box, .9]], person_teams={"100": 0})
        candidate["samples"].append(sample)
        secondary_id = 200 if order < 8 or not motion_change else 201
        secondary = deepcopy(sample)
        secondary["persons"][0][0] = secondary_id
        if missing and order == 8:
            secondary["persons"] = []
        support["samples"].append(secondary)
        raw["samples"].append(dict(order=order, frame_idx=order * 2))
        raw["detected_persons"][str(order)] = [dict(box=box, confidence=.9, color=color)]
    return raw, candidate, support


def test_joint_change_splits_without_changing_boxes_confidence_or_local_teams():
    raw, candidate, support = example()
    before = deepcopy((raw, candidate, support))
    output, stats = transform(raw, candidate, support, np.array([[30., 60., 190.], [220., 220., 220.]]), preserve_teams=True)
    assert len(stats["boundaries"]) == 1
    assert stats["boundaries"][0]["first_order"] == 8
    assert stats["boundaries"][0]["confirmed_order"] == 10
    ids = [s["persons"][0][0] for s in output["samples"]]
    assert ids == [100] * 8 + [101] * 8
    for original, actual in zip(candidate["samples"], output["samples"], strict=True):
        assert original["persons"][0][1:] == actual["persons"][0][1:]
        assert actual["person_teams"][str(actual["persons"][0][0])] == 0
    assert (raw, candidate, support) == before


@pytest.mark.parametrize("condition", ["same_motion", "brightness", "missing_motion"])
def test_one_source_or_brightness_alone_cannot_split_a_person(condition):
    raw, candidate, support = example(motion_change=condition != "same_motion",
                                     brightness_only=condition == "brightness", missing=condition == "missing_motion")
    output, stats = transform(raw, candidate, support, np.array([[30., 60., 190.], [220., 220., 220.]]), preserve_teams=True)
    assert not stats["boundaries"]
    assert output == candidate


def test_invented_candidate_box_is_rejected():
    raw, candidate, support = example()
    candidate["samples"][0]["persons"][0][1] += 1
    with pytest.raises(ValueError, match="invented"):
        transform(raw, candidate, support, np.array([[30., 60., 190.], [220., 220., 220.]]))
