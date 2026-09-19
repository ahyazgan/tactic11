"""Guard the experiment against invented boxes, -1 identities and hidden losses."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from scripts.soccertrack_v2.benchmark_tracker_backends import (
    BACKENDS,
    EvidenceTracker,
    backend_settings,
    pair_subset,
    regressions,
)


def config():
    return {"stats": {"effective_track_fps": 12.5},
            "config": {"lost_track_seconds": 1.5, "track_activation_threshold": .25}}


def test_external_lifetime_matches_actual_legacy_frames_without_double_scaling():
    baseline = backend_settings(config(), "supervision")
    frames = int(baseline["frame_rate"] / 30 * baseline["lost_track_buffer"])
    assert frames == 7
    for name in BACKENDS[1:]:
        values = backend_settings(config(), name)
        assert values["lost_track_buffer"] == frames
        assert values["frame_rate"] == 30
        assert values["high_conf_det_threshold"] == .25
    assert backend_settings(config(), "botsort")["enable_cmc"] is False


def test_unknown_backend_and_invalid_cadence_fail():
    with pytest.raises(ValueError, match="unknown"):
        backend_settings(config(), "made_up")
    data = config()
    data["stats"]["effective_track_fps"] = float("nan")
    with pytest.raises(ValueError, match="FPS"):
        backend_settings(data, "supervision")


def pair_score(passed=True, joined=False):
    return {"kit": dict(correct=2, wrong=0, unassigned=0, kit_boxes_missing=0, other_assigned=0),
            "pairs": {"fixture": {"covered_observations": 2,
                                  "counts": {"different_correct": int(passed), "false_join": int(joined)},
                                  "outcomes": [{"left": "a", "right": "b", "passed": passed}]}}}


def test_equal_aggregate_cannot_hide_loss_of_previously_correct_pair():
    before, after = pair_score(), pair_score(False)
    after["pairs"]["fixture"]["counts"] = before["pairs"]["fixture"]["counts"].copy()
    assert regressions(before, after) == ["fixture.a->b"]


def test_new_false_join_from_previously_uncovered_pair_is_a_regression():
    before, after = pair_score(False), pair_score(False, True)
    before["pairs"]["fixture"]["covered_observations"] = 0
    assert "fixture.false_join" in regressions(before, after)


def test_annotation_parts_are_excluded_by_source_box_not_predicted_identity():
    labels = {"observations": [dict(id="a", segment=0, frame_idx=2, bbox=[1, 2, 3, 4]),
                               dict(id="b", segment=0, frame_idx=2, bbox=[5, 6, 7, 8])],
              "pairs": [dict(left="a", right="b", relation="different")]}
    result = pair_subset(labels, {(0, (2, 1., 2., 3., 4.))})
    assert result["observations"] == [labels["observations"][1]]
    assert result["pairs"] == []
    assert len(labels["observations"]) == 2


@pytest.fixture
def detections():
    sv = pytest.importorskip("supervision")
    return sv.Detections(xyxy=np.array([[1., 2., 10., 20.], [30., 2., 40., 20.]]),
                         confidence=np.array([.8, .9]), class_id=np.array([0, 0]),
                         data={"raw_index": np.array([3, 7])})


def fake_adapter(output):
    return EvidenceTracker(SimpleNamespace(update=lambda _d: output, maximum_frames_without_update=7),
                           external=True)


def test_unconfirmed_ids_never_merge_into_a_shared_person(detections):
    output = deepcopy(detections)
    output.tracker_id = np.array([-1, 0])
    adapter = fake_adapter(output)
    result = adapter.update_with_detections(detections)
    assert result.tracker_id.tolist() == [1]
    assert result.data["raw_index"].tolist() == [7]
    assert adapter.unconfirmed == 1


@pytest.mark.parametrize("corruption", ["box", "confidence", "index", "duplicate_id"])
def test_tracker_cannot_rewrite_evidence(detections, corruption):
    output = deepcopy(detections)
    output.tracker_id = np.array([0, 1])
    if corruption == "box":
        output.xyxy[0, 0] += .01
    elif corruption == "confidence":
        output.confidence[0] -= .01
    elif corruption == "index":
        output.data["raw_index"][0] = 99
    else:
        output.tracker_id[:] = 0
    with pytest.raises(ValueError):
        fake_adapter(output).update_with_detections(detections)


@pytest.mark.parametrize("backend", BACKENDS)
def test_real_backends_keep_source_rows_and_recover_short_gap(detections, backend):
    sv = pytest.importorskip("supervision")
    settings = backend_settings(config(), backend)
    if backend == "supervision":
        tracker = sv.ByteTrack(**settings)
    else:
        trackers = pytest.importorskip("trackers")
        cls = dict(roboflow_byte=trackers.ByteTrackTracker,
                   botsort=trackers.BoTSORTTracker, ocsort=trackers.OCSORTTracker)[backend]
        tracker = cls(**settings)
    adapter = EvidenceTracker(tracker, external=backend != "supervision")
    for _ in range(4):
        first = adapter.update_with_detections(deepcopy(detections))
    identities = dict(zip(first.data["raw_index"], first.tracker_id, strict=True))
    for _ in range(2):
        empty = adapter.update_with_detections(detections[np.array([False, False])])
        assert len(empty) == 0
    after = adapter.update_with_detections(deepcopy(detections))
    assert dict(zip(after.data["raw_index"], after.tracker_id, strict=True)) == identities
    assert len(identities) == 2
    assert adapter.max_time_lost == 7


def test_in_place_input_mutation_cannot_evade_source_validation(detections):
    def mutate(data):
        data.xyxy[0, 0] += 1
        data.tracker_id = np.array([0, 1])
        return data

    adapter = EvidenceTracker(SimpleNamespace(update=mutate, maximum_frames_without_update=7),
                              external=True)
    with pytest.raises(ValueError, match="changed source"):
        adapter.update_with_detections(detections)
