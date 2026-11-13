"""Saha dışı pencere atlama: hangi pencere tutulur, hangi koşulda hiç uygulanmaz."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking import pitch_windows as pw
from app.tracking.calibration import PitchCalibration

# Görüntünün orta bandı saha: saha 105x68 m, görüntüde x 0-1050, y 200-880 pikselde.
CALIB = PitchCalibration.from_dict({
    "image_size": [1050, 1080],
    "points": [{"image": [0, 200], "pitch": [0, 0]}, {"image": [1050, 200], "pitch": [105, 0]},
               {"image": [1050, 880], "pitch": [105, 68]}, {"image": [0, 880], "pitch": [0, 68]}],
})


def test_pitch_grid_follows_the_calibration_and_its_margin():
    us, vs = pw.pitch_grid(CALIB, margin_m=0.0, step=20)
    assert vs.min() >= 200 and vs.max() <= 880 and us.min() == 0
    _, wide = pw.pitch_grid(CALIB, margin_m=2.0, step=20)
    assert wide.min() == 180 and wide.max() == 900  # 2 m = 20 px her yöne


def test_window_below_the_pitch_is_dropped_and_the_one_above_it_is_kept():
    points = pw.pitch_grid(CALIB, margin_m=0.0, step=20)
    offsets = np.array([
        [0, 0, 500, 150],      # sahanın üstünde, ama altındaki pencere boyunda saha var: gövdeler burada
        [0, 300, 500, 450],    # sahanın içinde
        [0, 930, 500, 1080],   # sahanın altında: ayağı burada olan oyuncu yok
    ])
    assert pw.windows_seeing_pitch(offsets, (500, 150), points).tolist() == [True, True, False]


def test_side_padding_keeps_a_window_just_beside_the_pitch():
    # Saha x 400-600 arasında; pencere 300-380'de, yan pay 0,15 x 200 = 30 px ile sahaya değer.
    points = (np.array([400.0, 600.0]), np.array([500.0, 500.0]))
    assert pw.windows_seeing_pitch(np.array([[180, 450, 380, 550]]), (200, 100), points).tolist() == [True]
    assert pw.windows_seeing_pitch(np.array([[100, 450, 300, 550]]), (200, 100), points).tolist() == [False]


@pytest.mark.parametrize(("windows", "batch"), [(55, 28), (42, 21), (43, 22), (1, 1), (0, 1)])
def test_kept_windows_are_split_into_two_balanced_groups(windows, batch):
    assert pw.balanced_batch(windows) == batch


def test_product_worker_applies_the_method_only_for_a_static_camera_with_a_calibration(monkeypatch):
    from scripts import track_video_product as product

    assert product.static_calibration_path(["--video", "v.mp4", "--camera", "static"]) is None  # kalibrasyon yok
    assert product.static_calibration_path(["--video", "v.mp4", "--calibration", "c.json",
                                            "--camera", "static"]) == "c.json"
    assert product.static_calibration_path(["--video", "v.mp4", "--calibration", "c.json",
                                            "--camera", "broadcast"]) is None
    assert product.static_calibration_path(["--video", "v.mp4", "--calibration", "c.json", "--camera", "static",
                                            "--per-frame-calibration", "on"]) is None

    from app.tracking import camera

    class _Verdict:
        def __init__(self, source_name):
            self.source_name = source_name

    monkeypatch.setattr(camera, "analyze_video", lambda path: _Verdict(camera.STATIC_SOURCE))
    assert product.static_calibration_path(["--video", "v.mp4", "--calibration", "c.json"]) == "c.json"
    monkeypatch.setattr(camera, "analyze_video", lambda path: _Verdict(camera.BROADCAST_SOURCE))
    assert product.static_calibration_path(["--video", "v.mp4", "--calibration", "c.json"]) is None
