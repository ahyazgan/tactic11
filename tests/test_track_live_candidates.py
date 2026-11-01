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
