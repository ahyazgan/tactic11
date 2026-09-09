"""scripts/track_live.py — sıcak model işçisi (WarmTracker).

Neden test: dedektör ilk `detect()` çağrısında kare boyutuna göre batch'ini
sabitleyip fp16 derliyor (app/tracking/detect.py `_prepare`). Model artık
segmentler arasında paylaşıldığı için, kaynak çözünürlük değişirse derlenmiş
sabit batch ile dilim sayısı uyuşmaz → sessizce yanlış/eksik tespit. Bu yüzden
çözünürlük değişince dedektör yeniden kurulmalı.

Torch/rfdetr ana venv'de yok; `RFDetrDetector` sahte bir sınıfla değiştirilir
(ağır import'lar zaten fonksiyon içinde, modül seviyesinde değil).
"""
from __future__ import annotations

import json

import pytest

from app.tracking import detect as detect_mod
from scripts.track_live import WarmTracker

CALIB = {
    "image_size": [3840, 2160],
    "pitch_length_m": 105, "pitch_width_m": 68,
    "points": [
        {"image": [0, 0], "pitch": [0, 0]},
        {"image": [3840, 0], "pitch": [105, 0]},
        {"image": [3840, 2160], "pitch": [105, 68]},
        {"image": [0, 2160], "pitch": [0, 68]},
    ],
}


class FakeDetector:
    """Kaç kez kurulduğunu sayar — gerçek model yüklenmez."""

    built = 0

    def __init__(self, cfg=None):
        FakeDetector.built += 1
        self.cfg = cfg


@pytest.fixture()
def warm(tmp_path, monkeypatch):
    FakeDetector.built = 0
    monkeypatch.setattr(detect_mod, "RFDetrDetector", FakeDetector)
    path = tmp_path / "calib.json"
    path.write_text(json.dumps(CALIB), encoding="utf-8")
    return WarmTracker(
        calibration=str(path),
        detector_cfg=detect_mod.DetectorConfig(tiles=6, threshold=0.3),
        pipeline_kwargs={"fps_out": 5.0, "track_fps": 15.0, "ball_threshold": 0.3},
    )


def test_model_is_loaded_once_across_segments(warm):
    """Asıl kazanç: ikinci segment modeli yeniden yüklemez."""
    first = warm._ensure_detector(3840, 2160)
    assert FakeDetector.built == 1
    assert warm.warmup_seconds >= 0.0

    for _ in range(4):
        again = warm._ensure_detector(3840, 2160)
        assert again is first, "aynı çözünürlükte dedektör yeniden kurulmamalı"
    assert FakeDetector.built == 1


def test_resolution_change_rebuilds_the_detector(warm, capsys):
    """Derlenmiş sabit batch eski çözünürlüğe ait — yeniden kurulmalı."""
    first = warm._ensure_detector(3840, 2160)
    second = warm._ensure_detector(1920, 1080)
    assert second is not first
    assert FakeDetector.built == 2
    assert "yeniden kuruluyor" in capsys.readouterr().out

    # Yeni çözünürlükte tekrar sıcak
    assert warm._ensure_detector(1920, 1080) is second
    assert FakeDetector.built == 2


def test_calibration_is_loaded_once_at_construction(warm):
    assert warm.calib is not None
    assert warm.calib.reprojection_error_m == pytest.approx(0.0, abs=1.0)
