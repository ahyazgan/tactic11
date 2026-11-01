from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.track_live_candidates import RecordingDetector


@dataclass
class FakeDetections:
    xyxy: np.ndarray
    confidence: np.ndarray
    class_id: np.ndarray

    def __getitem__(self, mask: np.ndarray) -> FakeDetections:
        return FakeDetections(self.xyxy[mask], self.confidence[mask], self.class_id[mask])


class FakeInner:
    person_ids = {1}
    ball_ids = {2}
    device = "cpu"

    def __init__(self) -> None:
        self.det = FakeDetections(np.array([[0, 0, 10, 30], [5, 5, 7, 7], [50, 50, 52, 52], [0, 0, 9, 25]], float),
                                  np.array([0.9, 0.15, 0.45, 0.2]), np.array([1, 2, 2, 1]))

    def detect(self, _rgb):
        return self.det

    def predict_single(self, _rgb):
        return self.det


def test_pipeline_sees_only_production_threshold() -> None:
    rec = RecordingDetector(FakeInner(), threshold=0.3)
    out = rec.detect(np.zeros((4, 4, 3)))
    assert out.confidence.tolist() == [0.9, 0.45]
    assert rec.predict_single(np.zeros((4, 4, 3))).confidence.tolist() == [0.9, 0.45]


def test_records_all_ball_candidates_and_delegates() -> None:
    rec = RecordingDetector(FakeInner(), threshold=0.3)
    assert rec.last_balls() == []
    rec.detect(np.zeros((4, 4, 3)))
    assert rec.last_balls() == [[6.0, 6.0, 0.15, 2.0, 2.0], [51.0, 51.0, 0.45, 2.0, 2.0]]
    assert rec.device == "cpu" and rec.ball_ids == {2}


def test_kit_recorder_medians_per_track() -> None:
    from app.tracking.kit_features import KitRecorder, torso_median_color

    rgb = np.zeros((100, 100, 3), np.uint8)
    rgb[:, :50] = (240, 230, 60)      # sarı forma solda
    rgb[:, 50:] = (40, 80, 200)       # mavi forma sağda
    rec = KitRecorder()
    for _ in range(3):
        rec.observe(rgb, [(1, 0, 0, 50, 100, 0.9), (2, 50, 0, 100, 100, 0.9)])
    s = rec.summary()
    assert s["1"]["n"] == 3 and s["1"]["median"] == [240.0, 230.0, 60.0]
    assert s["2"]["median"] == [40.0, 80.0, 200.0] and s["2"]["height_px"] == 100.0
    assert torso_median_color(rgb, (0, 0, 1, 2)) is None
