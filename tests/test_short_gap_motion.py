"""Guard source evidence, ambiguous recovery and the measured night-gap failure."""

import gzip
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from scripts.soccertrack_v2.benchmark_tracker_backends import backend_settings
from scripts.soccertrack_v2.candidates.palette_motion_partitions_v1 import partition
from scripts.soccertrack_v2.candidates.short_gap_motion_v1 import ShortGapMotionTracker, valid_color


def config():
    return dict(
        stats=dict(effective_track_fps=12.5),
        config=dict(lost_track_seconds=1.5, track_activation_threshold=0.25),
    )


def detection(x, confidence=0.4):
    sv = pytest.importorskip("supervision")
    return sv.Detections(
        xyxy=np.array([[float(x), 0.0, x + 30.0, 60.0]]),
        confidence=np.array([confidence]),
        data={"raw_index": np.array([0])},
    )


def lost_tracker():
    sv = pytest.importorskip("supervision")
    candidate = ShortGapMotionTracker(sv.ByteTrack(**backend_settings(config(), "supervision")))
    for x in (0, 5, 10, 15, 20):
        candidate.update_with_detections(detection(x), [[80, 95, 100]])
    candidate.update_with_detections(detection(0)[[]], [])
    track = candidate.primary.lost_tracks[0]
    # Isolate the observed-motion fallback from an intentionally lagging filter.
    track.mean[:2] = [30.0, 30.0]
    track.mean[4:6] = 0
    return candidate, track


def test_unique_recovery_keeps_source_rows_and_reset_clears_state():
    candidate, track = lost_tracker()
    source = detection(30)
    result = candidate.update_with_detections(source, [[80, 95, 100]])
    assert result.tracker_id.tolist() == [track.external_track_id]
    assert np.array_equal(source.xyxy, result.xyxy)
    assert np.array_equal(source.confidence, result.confidence)
    assert candidate.events[-1]["matched"] is True
    candidate.reset()
    assert not candidate.events and not candidate.history
    assert candidate.primary.frame_id == 0


@pytest.mark.parametrize(
    "color", [None, [float("nan"), 95, 100], [-1, 95, 100], [80, 95], [300, 95, 100]]
)
def test_invalid_color_cannot_recover_a_track(color):
    candidate, _ = lost_tracker()
    candidate.update_with_detections(detection(30), [color])
    assert not candidate.events
    assert valid_color(color) is None


def test_two_plausible_detections_do_not_choose_arbitrarily():
    candidate, _ = lost_tracker()
    sv = pytest.importorskip("supervision")
    options = sv.Detections.merge([detection(30), detection(31)])
    candidate.update_with_detections(options, [[80, 95, 100]] * 2)
    assert not candidate.events


def test_another_kit_cannot_steal_a_motion_proposal_via_higher_confidence():
    candidate, _ = lost_tracker()
    sv = pytest.importorskip("supervision")
    # Both old-motion costs fail. At the proposed position, the second (red)
    # box wins normal confidence-fused matching despite failing color support.
    options = sv.Detections.merge([detection(30, 0.4), detection(31, 0.55)])
    candidate.update_with_detections(options, [[80, 95, 100], [230, 20, 20]])
    assert not candidate.events


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_invalid_source_confidence_fails_before_advancing(confidence):
    candidate, _ = lost_tracker()
    before = candidate.primary.frame_id
    with pytest.raises(ValueError, match="confidence"):
        candidate.update_with_detections(detection(30, confidence), [[80, 95, 100]])
    assert candidate.primary.frame_id == before


def test_existing_normal_match_is_never_nudged_toward_a_second_box():
    candidate, track = lost_tracker()
    track.mean[:2] = [35.0, 30.0]
    sv = pytest.importorskip("supervision")
    options = sv.Detections.merge([detection(30), detection(31)])
    candidate.update_with_detections(options, [[80, 95, 100]] * 2)
    assert not candidate.events


def test_existing_rival_withholds_recovery():
    candidate, track = lost_tracker()
    rival = deepcopy(track)
    rival.external_track_id += 10
    candidate.primary.lost_tracks.append(rival)
    candidate.update_with_detections(detection(30), [[80, 95, 100]])
    assert not candidate.events


def test_nearby_rival_without_box_overlap_also_withholds_recovery():
    candidate, track = lost_tracker()
    rival = deepcopy(track)
    rival.external_track_id += 10
    rival.mean[:2] = [85.0, 30.0]
    candidate.primary.lost_tracks.append(rival)
    candidate.update_with_detections(detection(30), [[80, 95, 100]])
    assert not candidate.events


def test_failed_proposal_restores_normal_prediction(monkeypatch):
    candidate, track = lost_tracker()
    mean = track.mean.copy()
    mean[7] = 0
    expected_mean, expected_cov = candidate.primary.shared_kalman.predict(mean, track.covariance)
    original = candidate.primary.update_with_detections
    monkeypatch.setattr(candidate.primary, "update_with_detections", lambda d: original(d[[]]))
    candidate.update_with_detections(detection(30), [[80, 95, 100]])
    assert candidate.events[-1]["matched"] is False
    assert np.array_equal(track.mean, expected_mean)
    assert np.array_equal(track.covariance, expected_cov)


def test_expired_history_is_bounded_by_live_tracks():
    candidate, _ = lost_tracker()
    for _ in range(candidate.max_time_lost + 3):
        candidate.update_with_detections(detection(0)[[]], [])
    assert not candidate.history
    candidate.update_with_detections(detection(30), [[80, 95, 100]])
    assert not candidate.events


def test_ambiguous_duplicate_source_is_rejected_before_tracker_mutation():
    candidate, _ = lost_tracker()
    sv = pytest.importorskip("supervision")
    before = candidate.primary.frame_id
    with pytest.raises(ValueError, match="unique"):
        candidate.update_with_detections(
            sv.Detections.merge([detection(30), detection(30)]), [[80, 95, 100]] * 2
        )
    assert candidate.primary.frame_id == before


def palette_fixture():
    raw = {**config(), "samples": [], "detected_persons": {}}
    primary, secondary, baseline = ({"samples": []} for _ in range(3))
    for order in range(6):
        box = [float(order), 0.0, order + 20.0, 50.0]
        sample = dict(
            order=order,
            frame_idx=order * 2,
            seconds=order / 12.5,
            continuity_id=0,
            persons=[[13, *box, 0.8]],
            person_teams={"13": 0 if order < 3 else 1},
        )
        raw["samples"].append(deepcopy(sample))
        raw["detected_persons"][str(order)] = [
            dict(box=box, confidence=0.8, color=[90] * 3 if order < 3 else [180] * 3)
        ]
        primary["samples"].append(deepcopy(sample))
        baseline["samples"].append(deepcopy(sample))
        sample["persons"][0][0] = 7 if order < 3 else 8
        secondary["samples"].append(sample)
    return raw, primary, secondary, baseline, np.array([[90] * 3, [180] * 3])


def test_achromatic_palette_change_splits_only_after_independent_confirmation():
    args = palette_fixture()
    original = deepcopy(args[:4])
    output, events = partition(*args)
    assert len(events) == 1
    assert (events[0]["first_order"], events[0]["confirmed_order"]) == (3, 5)
    assert [s["persons"][0][0] for s in output["samples"]] == [13] * 3 + [14] * 3
    for before, after in zip(args[3]["samples"], output["samples"], strict=True):
        assert before["persons"][0][1:] == after["persons"][0][1:]
        assert list(before["person_teams"].values()) == list(after["person_teams"].values())
    assert args[:4] == original


@pytest.mark.parametrize(
    "missing", ["palette", "support", "after_confirmation", "continuity", "too_old"]
)
def test_incomplete_change_evidence_never_splits(missing):
    raw, primary, secondary, baseline, centers = palette_fixture()
    if missing == "palette":
        for rows in raw["detected_persons"].values():
            rows[0]["color"] = [90] * 3
    elif missing == "support":
        for s in secondary["samples"]:
            s["persons"][0][0] = 7
    elif missing == "after_confirmation":
        secondary["samples"].pop()
    elif missing == "continuity":
        for payload in (raw, primary, secondary, baseline):
            for s in payload["samples"][3:]:
                s["continuity_id"] = 1
    else:
        for payload in (raw, primary, secondary, baseline):
            for s in payload["samples"][3:]:
                s["seconds"] += 2
    _, events = partition(raw, primary, secondary, baseline, centers)
    assert not events


@pytest.mark.parametrize(
    "corruption", ["source_duplicate", "output_duplicate", "confidence", "time", "order", "fps"]
)
def test_source_ambiguity_and_fabricated_evidence_fail(corruption):
    raw, primary, secondary, baseline, centers = palette_fixture()
    if corruption == "source_duplicate":
        raw["detected_persons"]["0"] *= 2
    elif corruption == "output_duplicate":
        secondary["samples"][0]["persons"] *= 2
    elif corruption == "confidence":
        primary["samples"][0]["persons"][0][-1] = 0.9
    elif corruption == "time":
        secondary["samples"][1]["seconds"] = 1
    elif corruption == "order":
        primary["samples"].reverse()
    else:
        raw["stats"]["effective_track_fps"] = float("nan")
    with pytest.raises(ValueError):
        partition(raw, primary, secondary, baseline, centers)


def test_new_observation_has_no_invented_team():
    raw, primary, secondary, baseline, centers = palette_fixture()
    baseline["samples"][0]["persons"] = []
    output, _ = partition(raw, primary, secondary, baseline, centers)
    assert output["samples"][0]["person_teams"] == {"13": None}


def test_lost_baseline_observation_abstains_from_motion_for_whole_clip():
    raw, primary, secondary, baseline, centers = palette_fixture()
    primary["samples"][1]["persons"] = []
    source_inputs = deepcopy((primary, baseline))
    output, events = partition(raw, primary, secondary, baseline, centers)
    assert output["recovery_fallback"]["selected"] == "baseline"
    assert output["recovery_fallback"]["missing_observations"] == [
        dict(continuity_id=0, frame_idx=2, box=[1.0, 0.0, 21.0, 50.0])
    ]
    assert sum(len(s["persons"]) for s in output["samples"]) == 6
    # Independent palette refinement still works on retained baseline rows.
    assert len(events) == 1 and events[0]["first_order"] == 3
    assert (primary, baseline) == source_inputs


def replay_source_fixture(name):
    sv = pytest.importorskip("supervision")
    fixture = json.loads(gzip.decompress((Path(__file__).parent / "fixtures" / name).read_bytes()))
    raw = {**config(), "samples": [], "detected_persons": {}}
    primary = sv.ByteTrack(**backend_settings(fixture, "supervision"))
    recovery = ShortGapMotionTracker(sv.ByteTrack(**backend_settings(fixture, "supervision")))
    payloads = ({"samples": []}, {"samples": []})
    for s in fixture["samples"]:
        rows = s["detections"]
        source = sv.Detections(
            xyxy=np.array([r["box"] for r in rows]).reshape(-1, 4),
            confidence=np.array([r["confidence"] for r in rows]),
        )
        raw["detected_persons"][str(s["order"])] = rows
        raw["samples"].append({k: v for k, v in s.items() if k != "detections"})
        outputs = (
            primary.update_with_detections(deepcopy(source)),
            recovery.update_with_detections(deepcopy(source), [r["color"] for r in rows]),
        )
        for payload, output in zip(payloads, outputs, strict=True):
            sample = {k: v for k, v in s.items() if k != "detections"}
            sample["persons"] = [
                [int(t), *b.tolist(), float(c)]
                for t, b, c in zip(output.tracker_id, output.xyxy, output.confidence, strict=True)
            ]
            sample["person_teams"] = {str(t): 0 for t in output.tracker_id}
            payload["samples"].append(sample)
    return fixture, raw, payloads, recovery


def test_actual_crowded_night3_prefix_remains_exactly_baseline():
    _, _, (baseline, recovered), recovery = replay_source_fixture("short-gap-night3-crowd.json.gz")
    assert baseline == recovered
    assert not recovery.events


def test_actual_night84_full_warmup_repairs_gap_and_separates_later_white_player():
    fixture, raw, (baseline, recovered), recovery = replay_source_fixture(
        "short-gap-night84.json.gz"
    )

    def identity(payload, order, box):
        return next(r[0] for r in payload["samples"][order]["persons"] if r[1:5] == box)

    start = [r for r in baseline["samples"][187]["persons"] if r[0] == 16][0][1:5]
    end = [r for r in baseline["samples"][202]["persons"] if r[0] == 52][0][1:5]
    assert identity(baseline, 187, start) != identity(baseline, 202, end)
    assert identity(recovered, 187, start) == identity(recovered, 202, end) == 16
    assert any(e["order"] == 193 and e["track_id"] == 16 and e["matched"] for e in recovery.events)
    output, events = partition(
        raw,
        recovered,
        fixture["secondary"],
        baseline,
        np.array([[94.3, 101, 91.6], [176.1, 180.4, 174]]),
    )
    assert len(events) == 1 and events[0]["first_order"] == 236 and events[0]["raw_id"] == 16
    white = [r for r in recovered["samples"][236]["persons"] if r[0] == 16][0][1:5]
    assert identity(output, 236, white) != 16
