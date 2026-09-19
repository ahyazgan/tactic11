"""Production consensus retains primary observations and waits for joint evidence."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking.identity_consensus import ConsensusTeamAssigner, ConsensusTracker
from app.tracking.pipeline import PipelineConfig, SampledObservation
from app.tracking.teams import TeamAssignment
from app.tracking.tracker_config import tracker_context, validate_tracker_config


@pytest.mark.parametrize("motion_change,brightness,duplicate,expected_splits", [
    (True, False, False, 1), (False, False, False, 0), (True, True, False, 0), (True, False, True, 0)])
def test_production_splits_require_color_and_motion_and_preserve_evidence(motion_change, brightness, duplicate, expected_splits):
    assigner = ConsensusTeamAssigner()
    samples = []
    for order in range(16):
        box = [float(order), 0., float(order + 20), 50.]
        color = [30., 60., 190.] if order < 8 else ([15., 30., 95.] if brightness else [220., 220., 220.])
        sample = SampledObservation(order, order * 2, order / 10, [(100, *box, .9)], None)
        assigner.observe(100, np.asarray(color))
        secondary_id = 200 if order < 8 or not motion_change else 201
        secondary = SimpleNamespace(tracker_id=np.array([secondary_id]), xyxy=np.array([box]), confidence=np.array([.9]))
        if duplicate:
            secondary = SimpleNamespace(tracker_id=np.array([secondary_id, secondary_id + 10]),
                xyxy=np.array([box, box]), confidence=np.array([.9, .8]))
        assigner.record_frame(sample, secondary)
        samples.append(sample)
    before = deepcopy(samples)
    assignment = TeamAssignment({100: 0}, np.array([[30., 60., 190.], [220., 220., 220.]]), frozenset(), None)
    cfg = PipelineConfig(tracker_backend="consensus", filter_off_pitch_tracks=False)
    final, stats = assigner.refine(samples, assignment, SimpleNamespace(), cfg, 10.)
    assert len(stats["boundaries"]) == expected_splits
    assert not stats["boxes_removed"] and not stats["boxes_created"]
    for old, new in zip(before, samples, strict=True):
        assert old.persons[0][1:] == new.persons[0][1:]
        assert new.person_teams[str(new.persons[0][0])] == 0
        assert final.team_by_track[new.persons[0][0]] == 0
    if expected_splits:
        assert [s.persons[0][0] for s in samples] == [100] * 8 + [101] * 8
        assert stats["boundaries"][0]["confirmed_order"] == 10
    else:
        assert all(s.persons[0][0] == 100 for s in samples)


def test_two_trackers_receive_independent_source_rows_and_reset_together():
    sv = pytest.importorskip("supervision")
    calls = []

    class Primary:
        max_time_lost = 7

        def update_with_detections(self, detections):
            assert detections.xyxy[0, 0] == 0
            detections.tracker_id = np.array([10])
            return detections

        def reset(self):
            calls.append("primary")

    class Secondary:
        def update_with_detections(self, detections, bgr):
            detections.xyxy[0, 0] = 999
            detections.tracker_id = np.array([20])
            return detections

        def reset(self):
            calls.append("secondary")

    source = sv.Detections(xyxy=np.array([[0., 0., 20., 50.]]), confidence=np.array([.9]))
    tracker = ConsensusTracker(Primary(), Secondary())
    result = tracker.update_with_detections(source, np.zeros((50, 20, 3), np.uint8))
    assert result.tracker_id.tolist() == [10]
    assert source.xyxy[0, 0] == 0
    assert tracker.last_secondary.tracker_id.tolist() == [20]
    tracker.reset()
    assert calls == ["primary", "secondary"]
    assert tracker.last_secondary is None


@pytest.mark.parametrize("change", ["moving", "light", "refiner", "profile_refiner"])
def test_unsupported_consensus_combinations_are_rejected(change):
    cfg = PipelineConfig(tracker_backend="consensus")
    cal = SimpleNamespace(meta={})
    if change == "moving":
        cfg.per_frame_calibration = True
    elif change == "light":
        cfg.normalize_kit_light = True
    elif change == "refiner":
        cfg.refine_player_identities = True
    else:
        cal.meta["identity_profile"] = "fixed_camera_identity_v1"
    with pytest.raises(ValueError):
        validate_tracker_config(cfg, cal)


def test_live_state_profiles_cannot_mix_consensus_and_primary_reid(monkeypatch):
    from app.tracking import deepocsort

    monkeypatch.setattr(deepocsort, "verified_model_path", lambda _: Path("verified-model"))
    consensus = tracker_context("consensus", "model")
    reid = tracker_context("deepocsort", "model")
    assert consensus["tracker"]["profile"] != reid["tracker"]["profile"]
    assert consensus["tracker"]["model_sha256"] == reid["tracker"]["model_sha256"]
    assert tracker_context("supervision", "unused") == {}
