"""Camera discontinuities must not share identities, kit evidence or speeds."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration


def calibration():
    return PitchCalibration.from_dict({"image_size": [1300, 800], "points": [
        {"image": [x * 10 + 100, y * 10 + 50], "pitch": [x, y]}
        for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]
    ]})


@pytest.mark.parametrize("boundary", ["cut", "replay", "calibration", "none", "two_cuts"])
@pytest.mark.parametrize("real_tracker", [False, True])
def test_collection_resets_tracker_and_never_reuses_kit_history(monkeypatch, boundary, real_tracker):
    cal = calibration()
    sv = pytest.importorskip("supervision") if real_tracker else None

    class Detections:
        def __init__(self, boxes):
            self.xyxy = np.asarray(boxes).reshape(-1, 4)
            self.confidence = np.full(len(self.xyxy), .9)
            self.tracker_id = np.ones(len(self.xyxy), dtype=int)
        def __len__(self):
            return len(self.xyxy)
        def __getitem__(self, mask):
            return Detections(self.xyxy[mask])

    resets = []
    if sv is None:
        tracker = SimpleNamespace(update_with_detections=lambda d: d, reset=lambda: resets.append(1))
        monkeypatch.setitem(sys.modules, "supervision", SimpleNamespace(ByteTrack=lambda **kw: tracker))
    else:
        original_factory = sv.ByteTrack
        def real_factory(**kwargs):
            tracker = original_factory(**kwargs)
            original_reset = tracker.reset
            def reset():
                resets.append(1)
                original_reset()
            monkeypatch.setattr(tracker, "reset", reset)
            return tracker
        monkeypatch.setattr(sv, "ByteTrack", real_factory)

    def detections(boxes):
        if sv is None:
            return Detections(boxes)
        return sv.Detections(xyxy=np.asarray(boxes, dtype=float).reshape(-1, 4),
                             confidence=np.full(len(boxes), .9), class_id=np.zeros(len(boxes), dtype=int))
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(COLOR_RGB2BGR=1, cvtColor=lambda a, _: a))
    monkeypatch.setattr(pipeline, "video_info", lambda _: {"fps": 25., "width": 1300, "height": 800})
    monkeypatch.setattr(pipeline, "iter_video_frames", lambda *a: iter([
        (i, i * 2, i * .08, np.full((4, 4, 3), i)) for i in range(6)]))
    monkeypatch.setattr(pipeline, "kit_color", lambda rgb, *a, **kw: np.array(
        [200, 200, 200] if rgb[0, 0, 0] < 2 else [20, 60, 120]))
    detector = SimpleNamespace(detect=lambda rgb: int(rgb[0, 0, 0]), split=lambda index: (
        detections([[200, 100, 220, 150]]), detections([[206, 140, 214, 148]] if index < 2 else [])))
    roi_calls = []
    monkeypatch.setattr(pipeline, "_search_ball_roi", lambda *a: roi_calls.append(a[2]))

    class Calibrator:
        frames_calibrated = frames_rejected = anchor_attempts = anchors_found = reanchors = 0
        def mark_cut(self):
            pass
        def process(self, rgb):
            ok = not (boundary == "calibration" and rgb[0, 0, 0] == 2)
            self.frames_calibrated += ok
            self.frames_rejected += not ok
            return SimpleNamespace(ok=ok, calibration=cal, reason="missing field")

    class CutDetector:
        last_gray = None
        last_motion = None
        def update(self, rgb):
            self.last_gray = rgb
            return "cut" if (boundary in ("cut", "two_cuts") and rgb[0, 0, 0] == 2
                             or boundary == "two_cuts" and rgb[0, 0, 0] == 4) else None

    class ReplayFilter:
        mask_found = True
        def update(self, rgb, motion):
            return SimpleNamespace(is_replay=boundary == "replay" and rgb[0, 0, 0] == 2)

    monkeypatch.setitem(sys.modules, "app.tracking.camera", SimpleNamespace(CutDetector=CutDetector))
    monkeypatch.setitem(sys.modules, "app.tracking.replay", SimpleNamespace(ReplayFilter=ReplayFilter))
    cfg = pipeline.PipelineConfig(per_frame_calibration=True, detect_cuts=True,
                                  detect_replays=True, min_track_seconds=0)
    samples, teams, stats = pipeline.collect_observations("unused", cfg, detector=detector,
                                                       calib=cal, calibrator=Calibrator(), progress=False)
    expected_resets = 0 if boundary == "none" else 2 if boundary == "two_cuts" else 1
    assert len(resets) == stats["tracker_resets"] == expected_resets
    assert stats["calibration_gap_resets"] == int(boundary == "calibration")
    assert len(roi_calls) == (4 if boundary == "none" else 0)
    if boundary == "none":
        assert {s.persons[0][0] for s in samples} == {1}
        assert {s.continuity_id for s in samples} == {0}
    else:
        assert samples[0].persons[0][0] == 1
        assert samples[-1].persons[0][0] == expected_resets + 1
        assert len(teams._obs[1]) == 2
        assert all(np.array_equal(c, [200, 200, 200]) for c in teams._obs[1])
        assert all(np.array_equal(c, [20, 60, 120]) for c in teams._obs[2])
        for tid in teams._obs:
            assert len({s.continuity_id for s in samples if s.persons[0][0] == tid}) == 1


def test_velocities_use_only_neighbours_in_the_same_camera_shot():
    samples = [pipeline.SampledObservation(
        i, i, i * .2, [(1, x - 10, 100, x + 10, 150, .9)], (x, 150, .9), "det",
        continuity_id=int(i >= 2),
    ) for i, x in enumerate([200, 202, 500, 506])]
    players, ball = pipeline.compute_velocities(samples, calibration(), track_fps=5)
    assert [players[i][1] for i in range(4)] == [1., 1., 3., 3.]
    assert [ball[i] for i in range(4)] == [1., 1., 3., 3.]


def test_single_observation_per_shot_does_not_invent_speed():
    samples = [pipeline.SampledObservation(
        i, i, i * .2, [(1, 200 + i * 200, 100, 220 + i * 200, 150, .9)],
        (200 + i * 200, 150, .9), "det", continuity_id=i,
    ) for i in range(2)]
    players, ball = pipeline.compute_velocities(samples, calibration(), track_fps=5)
    assert players == {0: {}, 1: {}}
    assert ball == {}


def test_tracker_benchmark_matches_boxes_instead_of_changed_ids():
    from scripts.soccertrack_v2.benchmark_track_buffer import box_key, score_rows

    rows = [dict(segment=0, frame_idx=i, bbox=[0, 0, 10, 20], track=42, kit=kit)
            for i, kit in enumerate(["blue", "white"])]
    separated = {(0, box_key(r["frame_idx"], r["bbox"])): (i + 100, i) for i, r in enumerate(rows)}
    merged = {k: (100, team) for k, (_, team) in separated.items()}
    assert score_rows(rows, separated, 0)["correct"] == 2
    assert score_rows(rows, separated, 0)["conflicting_track_labels"] == 0
    assert score_rows(rows, merged, 0)["conflicting_track_labels"] == 1
    missing = score_rows(rows, {}, 0)
    assert missing["kit_boxes_missing"] == missing["unassigned"] == 2
