"""Hazır duruş kalibratörü: hattın kare sırasıyla duruş verir, olmayan kareyi atlatır."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from app.tracking import broadcast_calibrator as bc
from app.tracking.broadcast_calibrator import NO_POSE, BroadcastPoseCalibrator
from app.tracking.broadcast_two_pass import TwoPassTrack
from tests.test_camera_anchor import CAMERA, SIZE, main_poses

FRAME = np.zeros((4, 4, 3), np.uint8)


def test_poses_follow_the_frame_order_and_missing_frames_are_skipped():
    pose = main_poses(1)[0]
    track = TwoPassTrack(CAMERA, SIZE, poses={1: pose}, anchor_sources={"single_frame": 2, "grid": 1, "rejected": 4})
    calibrator = BroadcastPoseCalibrator(track)
    calibrator.mark_cut()
    first, second, third = (calibrator.process(FRAME) for _ in range(3))
    assert not first.ok and first.reason == NO_POSE and not third.ok
    assert second.ok and second.calibration.image_size == SIZE
    centre = np.array([SIZE[0] / 2, SIZE[1] * 0.6, 1.0]) @ pose.T
    assert np.allclose(second.calibration.image_to_pitch_m(SIZE[0] / 2, SIZE[1] * 0.6), centre[:2] / centre[2], atol=0.05)
    assert (calibrator.frames_calibrated, calibrator.frames_rejected, calibrator.calibrated_ratio) == (1, 2, 0.333)
    assert (calibrator.anchor_attempts, calibrator.anchors_found, calibrator.reanchors) == (7, 3, 0)


@dataclass
class Config:
    per_frame_calibration: bool = True
    detect_replays: bool = True
    track_fps: float = 15.0
    max_seconds: float | None = None


def wrapped(monkeypatch, track):
    calls = []

    def process_video(video, calib, **kwargs):
        calls.append(kwargs)
        return [], {}

    monkeypatch.setattr(bc, "calibrate_broadcast", lambda *_: BroadcastPoseCalibrator(track))
    return bc.two_pass_process_video(process_video), calls


def test_product_worker_hands_the_poses_to_the_pipeline_with_replay_filter_off(monkeypatch):
    track = TwoPassTrack(CAMERA, SIZE, poses={0: main_poses(1)[0]}, guard_rejected=3)
    run, calls = wrapped(monkeypatch, track)
    _, summary = run("v.mp4", None, cfg=Config(), match_id=1)
    assert calls[0]["cfg"].detect_replays is False and calls[0]["calibrator"].track is track and calls[0]["match_id"] == 1
    assert summary["broadcast_two_pass"]["guard_rejected"] == 3


def test_no_camera_or_fixed_camera_setup_produces_no_output(monkeypatch):
    run, calls = wrapped(monkeypatch, TwoPassTrack(None, SIZE))
    for cfg in (Config(), Config(per_frame_calibration=False)):
        with pytest.raises(SystemExit) as stop:
            run("v.mp4", None, cfg=cfg)
        assert stop.value.code == bc.EXIT_NO_CAMERA
    assert not calls
