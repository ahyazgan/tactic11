"""Hazır duruş kalibratörü: hattın kare sırasıyla duruş verir, olmayan kareyi atlatır."""
from __future__ import annotations

import numpy as np

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
