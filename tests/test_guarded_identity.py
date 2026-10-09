"""Keep old appearance evidence while adding achromatic palette transitions."""

import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.soccertrack_v2.benchmark_guarded_identity import (
    boundary_witnesses,
    known_configurations,
)
from scripts.soccertrack_v2.candidates.guarded_identity_v2 import partition


def scenario(colors, switch=7):
    raw = dict(
        stats=dict(effective_track_fps=10),
        config=dict(lost_track_seconds=1.5),
        samples=[],
        detected_persons={},
    )
    primary, secondary = dict(samples=[]), dict(samples=[])
    for order, color in enumerate(colors):
        box = [float(order), 0.0, float(order + 20), 50.0]
        sample = dict(order=order, frame_idx=order * 2, seconds=order / 10, continuity_id=0)
        raw["samples"].append(sample)
        raw["detected_persons"][str(order)] = [dict(box=box, confidence=0.9, color=color)]
        primary["samples"].append(
            dict(**sample, persons=[[100, *box, 0.9]], person_teams={"100": order % 2})
        )
        secondary["samples"].append(
            dict(**sample, persons=[[200 if order < switch else 201, *box, 0.9]])
        )
    return raw, primary, secondary


def test_two_cues_create_one_boundary_and_preserve_each_observation_team():
    raw, primary, secondary = scenario([[30.0, 60.0, 190.0]] * 7 + [[246.0, 246.0, 251.0]] * 9)
    original = deepcopy((raw, primary, secondary))
    output, events = partition(
        raw,
        primary,
        secondary,
        primary,
        [[30, 60, 190], [246, 246, 251]],
        baseline_centers=[[30, 60, 190], [246, 246, 251]],
    )
    assert len(events) == 1
    assert set(events[0]["evidence"]) == {"palette_crossover", "appearance_consensus"}
    assert events[0]["first_order"] == 7 and events[0]["confirmed_order"] == 9
    assert (raw, primary, secondary) == original
    for before, after in zip(primary["samples"], output["samples"], strict=True):
        row = after["persons"][0]
        assert row[1:] == before["persons"][0][1:]
        assert after["person_teams"][str(row[0])] == before["person_teams"]["100"]


def test_previous_white_six_lighting_case_is_not_split():
    colors = [
        [125.0, 171.0, 230.0],
        [125.0, 169.0, 228.0],
        [144.0, 177.0, 232.0],
        [151.0, 184.0, 236.0],
        [164.0, 194.0, 241.0],
        [173.0, 201.0, 245.0],
        [193.0, 214.0, 250.0],
    ]
    raw, primary, secondary = scenario(colors + [[246.0, 246.0, 251.0]] * 9)
    output, events = partition(
        raw,
        primary,
        secondary,
        primary,
        [[119.9, 149.7, 188.0], [205.4, 216.8, 235.5]],
        baseline_centers=[[119.9, 149.7, 188.0], [205.4, 216.8, 235.5]],
    )
    assert events == []
    assert output == primary


@pytest.mark.parametrize("unsupported", ["unchanged", "missing", "unstable"])
def test_neither_color_cue_can_replace_independent_identity_evidence(unsupported):
    raw, primary, secondary = scenario([[30.0, 60.0, 190.0]] * 7 + [[246.0, 246.0, 251.0]] * 9)
    for sample in secondary["samples"]:
        if unsupported == "missing":
            sample["persons"] = []
        else:
            sample["persons"][0][0] = 200 if unsupported == "unchanged" else sample["order"]
    output, events = partition(
        raw,
        primary,
        secondary,
        primary,
        [[30, 60, 190], [246, 246, 251]],
        baseline_centers=[[30, 60, 190], [246, 246, 251]],
    )
    assert events == [] and output == primary


def test_missing_primary_observation_uses_whole_baseline_before_combining():
    raw, primary, secondary = scenario([[30.0, 60.0, 190.0]] * 7 + [[246.0, 246.0, 251.0]] * 9)
    incomplete = deepcopy(primary)
    incomplete["samples"][0]["persons"] = []
    output, events = partition(
        raw,
        incomplete,
        secondary,
        primary,
        [[30, 60, 190], [246, 246, 251]],
        baseline_centers=[[30, 60, 190], [246, 246, 251]],
    )
    assert output["recovery_fallback"]["selected"] == "baseline"
    assert len(events) == 1
    assert len(output["samples"][0]["persons"]) == 1


def test_achromatic_transition_is_added_without_weakening_appearance_rule():
    raw, primary, secondary = scenario([[80.0, 85.0, 90.0]] * 7 + [[200.0, 205.0, 210.0]] * 9)
    anchors = [[80, 85, 90], [200, 205, 210]]
    _, legacy = partition(
        raw, primary, secondary, primary, anchors, baseline_centers=anchors, appearance_only=True
    )
    _, combined = partition(raw, primary, secondary, primary, anchors, baseline_centers=anchors)
    assert legacy == []
    assert len(combined) == 1 and combined[0]["evidence"] == ["palette_crossover"]


@pytest.mark.parametrize("case_index", range(7))
def test_actual_old_boundary_history_preserves_six_splits_and_white_six(case_index):
    fixture = json.loads(
        gzip.decompress(
            (
                Path(__file__).parent / "fixtures/guarded-identity-old-boundaries.json.gz"
            ).read_bytes()
        )
    )
    case = fixture["cases"][case_index]
    base = case["baseline"]
    output, events = partition(
        case["raw"],
        base,
        case["secondary"],
        base,
        case["anchors"],
        baseline_centers=case["appearance_centers"],
    )
    assert len(events) == int(case["expected_split"]), (case["group"], case["segment"], events)
    if events:
        assert events[0]["first_order"] == case["boundary"]["first_order"]
        assert events[0]["confirmed_order"] == case["boundary"]["confirmed_order"]
    for before, after in zip(base["samples"], output["samples"], strict=True):
        assert len(before["persons"]) == len(after["persons"])
        for old, new in zip(before["persons"], after["persons"], strict=True):
            assert old[1:] == new[1:]
            assert before["person_teams"][str(old[0])] == after["person_teams"][str(new[0])]


def test_known_set_includes_both_consumed_control_generations():
    configs = known_configurations()
    assert sum(len(cfg["segments"]) for cfg in configs.values()) == 19
    assert configs["consensus_day"]["segments"] == [60, 62]
    assert configs["consensus_night"]["segments"] == [80, 82]
    assert configs["palette_day"]["segments"] == [64, 66]
    assert configs["palette_night"]["segments"] == [78, 84]


def test_boundary_witness_uses_source_boxes_and_rejects_missing_or_rejoined_evidence():
    raw, primary, secondary = scenario([[30.0, 60.0, 190.0]] * 7 + [[246.0, 246.0, 251.0]] * 9)
    output, _ = partition(
        raw,
        primary,
        secondary,
        primary,
        [[30, 60, 190], [246, 246, 251]],
        baseline_centers=[[30, 60, 190], [246, 246, 251]],
    )
    historical = {
        "development": {
            "reports": [
                dict(
                    group="closed_day",
                    segment=60,
                    choices=[
                        dict(
                            accepted=True,
                            boundary=dict(
                                continuity_id=0,
                                raw_id=100,
                                first_order=7,
                                confirmed_order=9,
                            ),
                        )
                    ],
                )
            ]
        }
    }
    for sample in output["samples"]:
        sample["persons"][0][0] += 500  # IDs may be renumbered; boxes are the witness.
    assert boundary_witnesses("consensus_day", 60, primary, output, historical)[0]["preserved"]
    missing = deepcopy(output)
    missing["samples"][8]["persons"] = []
    assert not boundary_witnesses("consensus_day", 60, primary, missing, historical)[0]["preserved"]
    assert not boundary_witnesses("consensus_day", 60, primary, primary, historical)[0]["preserved"]
