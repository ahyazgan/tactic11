"""Direct-kit benchmark must preserve selection, abstentions and test separation."""
from __future__ import annotations

import json

import numpy as np
import pytest

from scripts.soccertrack_v2.benchmark_kit_colors import (
    benchmark,
    color_observations,
    passes_gate,
    score,
)
from scripts.soccertrack_v2.prepare_kit_review import select_samples


def test_sample_selection_uses_fixed_time_and_all_people_without_predictions():
    payload = {"segment": 0, "video": "clip.mp4", "samples": [
        {"frame_idx": 124, "seconds": 4.96, "persons": [[1, 0, 0, 10, 20, .1], [2, 20, 0, 30, 20, .9]]},
        {"frame_idx": 126, "seconds": 5.04, "persons": [[3, 0, 0, 10, 20, .9]]},
        {"frame_idx": 500, "seconds": 20.0, "persons": [[1, 10, 0, 20, 20, .5]]},
    ]}
    rows = select_samples(payload, [5.0, 20.0, 5.0])
    assert [r["id"] for r in rows] == ["0-124-1", "0-124-2", "0-500-1"]
    assert all(r["kit"] is None and "prediction" not in r for r in rows)


def test_bright_quarter_keeps_minimum_evidence_and_ignores_dark_majority():
    colors = np.array([[10, 20, 10]] * 7 + [[100, 90, 90], [200, 180, 180]])
    original = colors.copy()
    selected = color_observations(colors, "bright_quarter")
    # ceil(9/4)=3: no per-channel mixture of different observations.
    assert len(selected) == 3
    np.testing.assert_array_equal(selected[-2:], colors[-2:])
    np.testing.assert_array_equal(colors, original)
    assert len(color_observations(colors[:1], "bright_quarter")) == 1
    assert len(color_observations(colors[:2], "bright_quarter")) == 2
    assert len(color_observations(colors[:0], "bright_quarter")) == 0
    np.testing.assert_array_equal(color_observations(colors, "median"), colors)


def test_score_does_not_turn_abstention_into_correct_or_drop_other_kits():
    rows = [{"segment": 0, "track": i, "kit": kit}
            for i, kit in enumerate(["blue", "white", "white", "other", "uncertain"])]
    predictions = {(0, 0): 0, (0, 1): 0, (0, 2): None, (0, 3): 1, (0, 4): 1}
    assert score(rows, predictions, 0) == {
        "samples": 5, "labeled_players": 3, "correct": 1, "wrong": 1,
        "unassigned_players": 1, "other_people": 1, "other_assigned": 1, "uncertain": 1,
    }


def test_control_labels_cannot_change_team_mapping_or_predictions(tmp_path):
    rows = []
    for segment in (0, 3, 6, 9):
        payload = {"colors": {"1": [[30, 40, 200]] * 4, "2": [[200, 200, 200]] * 4},
                   "samples": [{"persons": [[1], [2]]}]}
        (tmp_path / f"seg_{segment:04d}.json").write_text(json.dumps(payload))
        rows.extend([{"id": f"{segment}-{track}", "segment": segment, "track": track, "kit": kit}
                     for track, kit in ((1, "blue"), (2, "white"))])
    before = benchmark(tmp_path, rows)
    flipped = [{**r, "kit": "white" if r["kit"] == "blue" else "blue"}
               if r["segment"] in (6, 9) else r for r in rows]
    after = benchmark(tmp_path, flipped)
    for variant in before:
        assert before[variant]["predictions"] == after[variant]["predictions"]
        assert before[variant]["blue_team_from_development"] == after[variant]["blue_team_from_development"]
        assert before[variant]["development"] == after[variant]["development"]
        assert before[variant]["control"]["correct"] == 4
        assert after[variant]["control"]["wrong"] == 4


@pytest.mark.parametrize("change,passes", [
    ({"correct": 65, "wrong": 5, "unassigned_players": 4}, False),
    ({"correct": 68, "wrong": 5, "unassigned_players": 1}, True),
    ({"correct": 67, "wrong": 8}, False),
    ({"correct": 67, "other_assigned": 4}, False),
    ({"correct": 67, "samples": 80}, False),
])
def test_acceptance_requires_real_gain_on_the_same_population(change, passes):
    before = {"samples": 81, "labeled_players": 74, "other_people": 7, "uncertain": 0,
              "correct": 66, "wrong": 7, "unassigned_players": 1, "other_assigned": 3}
    assert passes_gate(before, {**before, **change}) is passes
