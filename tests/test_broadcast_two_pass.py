"""İki geçişli yayın takibi: kamera yalnız ilk geçişten, bekçi ikinci geçişin her duruşunda."""
from __future__ import annotations

import numpy as np

from app.tracking import broadcast_two_pass as tp
from app.tracking.broadcast_track import TrackFrame
from tests.test_camera_anchor import CAMERA, SIZE, main_poses, pose_from

OTHER = np.array([20.0, -30.0, -8.0])
FRAME = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)


class FakeAnchor:
    def __init__(self, camera: np.ndarray, size: tuple[int, int]) -> None:
        self.stats = {"single_frame": 1}


def fake_tracker(first: dict[int, np.ndarray], second: dict[int, np.ndarray]):
    class Tracker:
        def __init__(self, fps: float = 15.0, *, filters: bool = True, anchor=None) -> None:
            self._poses = first if filters else second
            assert (anchor is None) == filters

        def feed(self, k: int, bgr: np.ndarray) -> list[tuple[int, TrackFrame]]:
            pose = self._poses.get(k)
            return [(k, TrackFrame(pose, "tracked" if pose is not None else "no_anchor"))]

    return Tracker


def reader(count: int, calls: list[int]):
    def frames():
        calls.append(1)
        return ((k, FRAME) for k in range(0, count * tp.CAMERA_EVERY_FRAMES, tp.CAMERA_EVERY_FRAMES))

    return frames


def test_guard_drops_a_pose_the_camera_cannot_explain(monkeypatch):
    main = dict(zip(range(0, 12 * 45, 45), main_poses(12), strict=True))
    second = {**main, 7: main_poses(3)[1], 45: pose_from(OTHER, (40.0, 30.0), 3000.0)}
    monkeypatch.setattr(tp, "BackfillingTracker", fake_tracker(main, second))
    monkeypatch.setattr(tp, "CameraPriorAnchor", FakeAnchor)
    calls: list[int] = []
    track = tp.track_two_pass(reader(12, calls))
    assert len(calls) == 2
    assert np.allclose(track.camera, CAMERA, atol=1.0)
    assert 45 not in track.poses and track.guard_rejected == 1
    assert set(track.poses) == set(main) - {45}
    assert track.states == {"tracked": 12} and track.anchor_sources == {"single_frame": 1}
    assert track.size == SIZE


def test_no_camera_means_no_poses_and_no_second_pass(monkeypatch):
    few = dict(zip(range(0, 5 * 45, 45), main_poses(5), strict=True))
    monkeypatch.setattr(tp, "BackfillingTracker", fake_tracker(few, few))
    calls: list[int] = []
    track = tp.track_two_pass(reader(5, calls))
    assert track.camera is None and track.poses == {} and len(calls) == 1
