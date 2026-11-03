"""Kamera önselli çapa: konum bulma, artık ve ikinci karar kapısı."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking import camera_anchor as ca
from app.tracking.broadcast_anchor import BroadcastAnchor
from app.tracking.pitch_model import model_points

SIZE = (1920, 1080)
MAIN = np.array([52.0, 110.0, -20.0])
CAMERA = np.array([52.0, 110.0, 20.0])


def pose_from(center: np.ndarray, target: tuple[float, float], focal: float) -> np.ndarray:
    """Bu kameradan sahaya bakan görüntü→saha duruşu. Saha çerçevesi sağ elli, z aşağı."""
    forward = np.array([target[0], target[1], 0.0]) - center
    forward /= np.linalg.norm(forward)
    down = np.array([0.0, 0.0, 1.0]) - forward[2] * forward
    down /= np.linalg.norm(down)
    right = np.cross(down, forward)
    rotation = np.vstack([right, down, forward])
    k = np.array([[focal, 0, SIZE[0] / 2], [0, focal, SIZE[1] / 2], [0, 0, 1.0]])
    return np.linalg.inv(k @ np.c_[rotation[:, :2], -rotation @ center])


def main_poses(count: int) -> list[np.ndarray]:
    return [pose_from(MAIN, (20 + 5.0 * i, 25 + (i % 3) * 8.0), 2600 + 120.0 * i) for i in range(count)]


def rendered(pose: np.ndarray) -> np.ndarray:
    """Duruştan çizgi maskesi: saha çizgileri görüntüye çizilir."""
    import cv2

    pts = model_points(0.05)
    points = np.c_[pts, np.ones(len(pts))] @ np.linalg.inv(pose).T
    pixels = np.round(points[:, :2] / points[:, 2:3]).astype(int)
    inside = (pixels[:, 0] >= 0) & (pixels[:, 0] < SIZE[0]) & (pixels[:, 1] >= 0) & (pixels[:, 1] < SIZE[1])
    mask = np.zeros((SIZE[1], SIZE[0]), np.uint8)
    mask[pixels[inside, 1], pixels[inside, 0]] = 255
    return cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0


def rejecting(best: np.ndarray | None):
    return lambda _m, _g=None, _t=None: BroadcastAnchor(None, False, "test", best_homography=best)


def test_camera_position_is_recovered_from_a_pose():
    found = ca.camera_position(main_poses(1)[0], SIZE)
    assert found is not None
    assert np.allclose(found, CAMERA, atol=1e-6)


def test_residual_is_near_zero_from_the_true_camera_and_large_from_elsewhere():
    pose = main_poses(1)[0]
    assert ca.pose_residual_m(pose, CAMERA, SIZE) < 0.3
    assert ca.pose_residual_m(pose, np.array([5.0, 40.0, 8.0]), SIZE) > 2.0


def test_camera_needs_enough_poses():
    assert ca.locate_camera(main_poses(ca.MIN_POSES - 1), SIZE) is None
    found = ca.locate_camera(main_poses(ca.MIN_POSES), SIZE)
    assert found is not None
    assert np.linalg.norm(found - CAMERA) < 1.5


def test_grid_poses_come_from_the_camera():
    grid = ca.pose_grid(CAMERA, SIZE)
    for g in grid[:: len(grid) // 5]:
        assert ca.pose_residual_m(np.linalg.inv(g), CAMERA, SIZE) < 0.5


def test_single_frame_acceptance_is_not_changed(monkeypatch):
    accepted = BroadcastAnchor(np.eye(3), True, "ok", inlier=0.9)
    monkeypatch.setattr(ca, "find_broadcast_anchor", lambda _m, _g=None, _t=None: accepted)
    prior = ca.CameraPriorAnchor(CAMERA, SIZE)
    assert prior(np.zeros((SIZE[1], SIZE[0]), bool)) is accepted
    assert prior.stats["single_frame"] == 1


def test_best_pose_from_the_camera_becomes_an_anchor(monkeypatch):
    pytest.importorskip("cv2")
    truth = pose_from(MAIN, (30.0, 30.0), 2600.0)
    monkeypatch.setattr(ca, "find_broadcast_anchor", rejecting(truth))
    prior = ca.CameraPriorAnchor(CAMERA, SIZE)
    result = prior(rendered(truth))
    assert result.accepted and result.note == "camera_prior_best_pose"
    assert np.allclose(result.homography, truth)


def test_grid_finds_the_pose_when_no_hypothesis_is_right(monkeypatch):
    pytest.importorskip("cv2")
    truth = pose_from(MAIN, (30.0, 30.0), 2600.0)
    monkeypatch.setattr(ca, "find_broadcast_anchor", rejecting(None))
    prior = ca.CameraPriorAnchor(CAMERA, SIZE)
    result = prior(rendered(truth))
    assert result.accepted and result.note == "camera_prior_grid"
    found = np.array([960.0, 800.0, 1.0]) @ result.homography.T
    want = np.array([960.0, 800.0, 1.0]) @ truth.T
    assert np.linalg.norm(found[:2] / found[2] - want[:2] / want[2]) < 2.0


def test_pose_from_another_camera_stays_rejected(monkeypatch):
    pytest.importorskip("cv2")
    other = pose_from(np.array([100.0, 95.0, -8.0]), (70.0, 30.0), 3000.0)
    monkeypatch.setattr(ca, "find_broadcast_anchor", rejecting(other))
    monkeypatch.setattr(ca.CameraPriorAnchor, "_grid_winner", lambda *_a: None)
    prior = ca.CameraPriorAnchor(CAMERA, SIZE)
    result = prior(rendered(other))
    assert not result.accepted
    assert prior.stats["rejected"] == 1


def test_empty_mask_is_rejected_without_a_search(monkeypatch):
    monkeypatch.setattr(ca, "find_broadcast_anchor", rejecting(None))
    monkeypatch.setattr(ca.CameraPriorAnchor, "_grid_winner", lambda *_a: pytest.fail("arama olmamalı"))
    prior = ca.CameraPriorAnchor(CAMERA, SIZE)
    assert not prior(np.zeros((SIZE[1], SIZE[0]), bool)).accepted
