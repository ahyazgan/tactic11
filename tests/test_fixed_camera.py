"""Sabit kamera bekçisi: aynı kameradan gelen duruş kalır, başka konumdan gelen reddedilir (cv2'siz)."""
from __future__ import annotations

import numpy as np

from app.tracking.fixed_camera import camera_position, guard_poses, pose_residual_m

SIZE = (1920, 1080)
MAIN = np.array([52.0, 110.0, -20.0])


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


def test_camera_position_is_recovered_from_a_pose():
    found = camera_position(main_poses(1)[0], SIZE)
    assert found is not None
    assert np.allclose(found, [52, 110, 20], atol=1e-6)


def test_residual_is_near_zero_from_the_true_camera_and_large_from_elsewhere():
    pose = main_poses(1)[0]
    assert pose_residual_m(pose, np.array([52.0, 110.0, 20.0]), SIZE) < 0.3
    assert pose_residual_m(pose, np.array([5.0, 40.0, 8.0]), SIZE) > 2.0


def test_guard_keeps_main_camera_and_rejects_another_camera():
    other = pose_from(np.array([100.0, 95.0, -8.0]), (70.0, 30.0), 3000.0)
    kept = guard_poses([*main_poses(12), other], SIZE)
    assert kept == [True] * 12 + [False]


def test_guard_rejects_everything_with_too_few_poses():
    assert guard_poses(main_poses(9), SIZE) == [False] * 9
