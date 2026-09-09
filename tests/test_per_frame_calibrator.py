"""PerFrameCalibrator — kamera takibinin güvenlik kuralları.

Bu sınıfın işi doğru homografiyi bulmak kadar, **bulamadığında susmaktır**.
Sahanın paralel çizgileri birbirine benzediği için homografi yanlış çizgiye
kilitlenebilir; ölçüldü, böyle oturmalar %55 inlier alıyor (doğru oturmalardan
biri %58) — yani skor tek başına ayırmıyor. Ayıran şey fizik: yanlış çözüm bir
karede 36 m sıçrıyor.

cv2 gerekmez: `process_lines` mesafe haritasını doğrudan alır.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.calibration import dlt_homography
from app.tracking.homography_fit import project_to_image
from app.tracking.pitch_lines import (
    MIN_LINE_PIXELS,
    PerFrameCalibrator,
    calibration_from_homography,
)
from app.tracking.pitch_model import model_points, pitch_corners

W, H = 960, 540
BASE_CORNERS = np.array(
    [[120.0, 150.0], [840.0, 150.0], [930.0, 470.0], [30.0, 470.0]], dtype=float,
)


def homography_for(offset=(0.0, 0.0)) -> np.ndarray:
    return dlt_homography(BASE_CORNERS + np.array(offset), pitch_corners())


def dist_map_for(h: np.ndarray) -> np.ndarray:
    """Verilen homografinin çizgilerinden mesafe haritası (kaba chamfer)."""
    mask = np.zeros((H, W), dtype=bool)
    for u, v in project_to_image(h, model_points(0.25)):
        if not (np.isfinite(u) and np.isfinite(v)):
            continue
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < W and 0 <= vi < H:
            mask[max(0, vi - 2):vi + 3, max(0, ui - 2):ui + 3] = True
    d = np.where(mask, 0.0, 60.0)
    for _ in range(2):
        for axis in (0, 1):
            for direction in (1, -1):
                shifted = np.roll(d, direction, axis=axis)
                if direction == 1:
                    shifted[0, :] = 60.0 if axis == 0 else shifted[0, :]
                    if axis == 1:
                        shifted[:, 0] = 60.0
                else:
                    shifted[-1, :] = 60.0 if axis == 0 else shifted[-1, :]
                    if axis == 1:
                        shifted[:, -1] = 60.0
                d = np.minimum(d, shifted + 1.0)
    return d


def line_pixels_of(dmap: np.ndarray) -> int:
    return int((dmap == 0.0).sum())


@pytest.fixture()
def calibrator():
    anchor = calibration_from_homography(homography_for(), (W, H))
    return PerFrameCalibrator(anchor, image_size=(W, H))


def _feed(cal: PerFrameCalibrator, h: np.ndarray):
    d = dist_map_for(h)
    return cal.process_lines(d, line_pixels=line_pixels_of(d))


def test_tracks_a_slowly_panning_camera(calibrator) -> None:
    """Asıl iş: kamera azar azar kayarken homografi peşinden gitmeli."""
    results = [_feed(calibrator, homography_for((k * 6.0, k * 2.0))) for k in range(5)]
    assert all(r.ok for r in results), [r.reason for r in results if not r.ok]
    assert calibrator.calibrated_ratio == 1.0
    assert calibrator.tracking


def test_rejects_a_physically_impossible_jump(calibrator) -> None:
    """Bir karede sahanın öbür ucuna atlayan sahne reddedilmeli ve takip kopmalı.

    Hangi kapının yakaladığı (oturma kalitesi mi, fizik mi) duruma göre değişir;
    garanti edilen şey ÇIKTI ÜRETİLMEMESİDİR.
    """
    assert _feed(calibrator, homography_for()).ok
    far = _feed(calibrator, homography_for((300.0, 120.0)))
    assert not far.ok, far.reason
    assert far.calibration is None
    assert not calibrator.tracking


def test_jump_gate_measures_real_pitch_distance(calibrator) -> None:
    """Sıçrama ölçüsü METRE cinsinden olmalı — piksel değil.

    Gerçek videoda yanlış çizgiye kilitlenen oturmalar %55 inlier alıyordu
    (doğrulardan biri %58), yani skor ayırmıyordu; ayıran şey bir karede 36 m
    sıçramanın fiziksel imkânsızlığıydı.
    """
    same = calibrator._jump_m(homography_for(), homography_for())
    assert same is not None and same < 0.01

    small = calibrator._jump_m(homography_for((6.0, 0.0)), homography_for())
    big = calibrator._jump_m(homography_for((300.0, 120.0)), homography_for())
    assert small is not None and big is not None
    assert small < calibrator.MAX_PITCH_JUMP_M < big


def test_close_up_without_lines_is_skipped_not_guessed(calibrator) -> None:
    """Yakın çekim/replay: çizgi yok → kare atlanır, uydurma konum üretilmez."""
    blank = np.full((H, W), 60.0, dtype=float)
    res = calibrator.process_lines(blank, line_pixels=MIN_LINE_PIXELS - 1,
                                   grass_ratio=0.1)
    assert not res.ok
    assert "saha çizgisi bulunamadı" in res.reason
    assert calibrator.frames_rejected == 1


def test_stays_lost_until_re_anchored(calibrator) -> None:
    """Kesme sonrası otomatik yakalama KAPALI — dışarıdan çapa beklenir.

    Otomatik yakalama denendiğinde iki ardışık kare aynı yanlış çizgiye
    kilitlenip birbirini doğruluyordu (hata 499 m'ye çıktı).
    """
    assert _feed(calibrator, homography_for()).ok
    assert not _feed(calibrator, homography_for((300.0, 120.0))).ok   # kesme
    # Kesme sonrası yeni sahne KENDİ İÇİNDE tutarlı olsa bile kabul edilmemeli
    for _ in range(3):
        r = _feed(calibrator, homography_for((300.0, 120.0)))
        assert not r.ok, r.reason
        assert r.calibration is None

    # Çapa yenilenince yeniden takibe girer
    calibrator._anchor = calibration_from_homography(homography_for((300.0, 120.0)), (W, H))
    calibrator.reset_to_anchor()
    assert _feed(calibrator, homography_for((300.0, 120.0))).ok
    assert calibrator.tracking


def test_produces_a_usable_calibration_object(calibrator) -> None:
    """Dönen nesne hattın geri kalanının beklediği PitchCalibration olmalı."""
    res = _feed(calibrator, homography_for((8.0, 3.0)))
    assert res.ok and res.calibration is not None
    x, y = res.calibration.image_to_pitch_m(W / 2, H / 2)
    assert 0.0 <= x <= 105.0 and 0.0 <= y <= 68.0
    assert res.fit is not None and res.fit.inlier_ratio > 0.5
