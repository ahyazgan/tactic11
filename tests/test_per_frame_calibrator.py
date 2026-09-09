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


def test_reacquire_searches_from_the_anchor_not_the_drifted_pose() -> None:
    """Yeniden yakalama açıkken arama ÇAPADAN yapılır.

    Kaymış son homografiden serbest aramak, 180° ikizine kilitlenme riski
    taşır (saha modeli tam simetrik). Çapa hangi yarı olduğunu sabitler.
    """
    anchor_h = homography_for()
    cal = PerFrameCalibrator(
        calibration_from_homography(anchor_h, (W, H)),
        image_size=(W, H), allow_reacquire=True,
    )
    assert _feed(cal, anchor_h).ok
    # Kesme: çok uzak sahne → takip kopar
    assert not _feed(cal, homography_for((300.0, 120.0))).ok
    assert not cal.tracking
    # Kamera çapaya yakın görüntüye döndü → yeniden yakalanmalı
    back = _feed(cal, homography_for((10.0, 4.0)))
    assert back.ok, back.reason
    assert cal.tracking


def test_reacquire_stays_closed_by_default() -> None:
    """Varsayılan güvenli: yeniden yakalama kapalı, dışarıdan çapa beklenir."""
    cal = PerFrameCalibrator(
        calibration_from_homography(homography_for(), (W, H)), image_size=(W, H),
    )
    assert _feed(cal, homography_for()).ok
    assert not _feed(cal, homography_for((300.0, 120.0))).ok
    back = _feed(cal, homography_for((10.0, 4.0)))
    assert not back.ok
    assert "çapa" in back.reason, back.reason


# --- kesme bildirimi (TV yayını) ------------------------------------------- #

def test_mark_cut_drops_out_of_tracking(calibrator) -> None:
    """Kesme = süreklilik KOPTU. Kalibratör bunu bilmeli.

    Kritik ayrım: TAKİPTE yolundaki kabul kapısı FİZİKTİR ("sabit bir görüntü
    noktası bir karede 5 m'den fazla oynayamaz"). Kesmede o varsayım geçersiz;
    iki ayrı kameranın kareleri arasında süreklilik yoktur. Kesmeyi "takip
    sürüyor" saymak, fizik kapısını anlamsız bir referansa uygulamaktır.
    """
    assert _feed(calibrator, homography_for()).ok
    assert calibrator.tracking

    calibrator.mark_cut()
    assert not calibrator.tracking


def test_reset_to_anchor_and_mark_cut_differ(calibrator) -> None:
    """İkisi karıştırılmamalı: biri takibi sürdürür, öbürü kopartır.

    `reset_to_anchor` elle yeniden çapalama içindir (dışarıdan "bu kare çapaya
    benziyor" bilgisi gelir). `mark_cut` ise kesme içindir.
    """
    assert _feed(calibrator, homography_for()).ok
    calibrator.reset_to_anchor()
    assert calibrator.tracking, "elle çapalama takibi sürdürmeli"

    calibrator.mark_cut()
    assert not calibrator.tracking, "kesme takibi kopartmalı"


def test_cut_then_recovery_needs_reacquire_enabled(calibrator) -> None:
    """Yeniden yakalama kapalıyken kesme KALICI kayıptır.

    TV yayını için ölümcül olan tam bu: yayın sürekli kamera değiştirir, ilk
    kesmeden sonra segmentin kalanındaki her kare atılır.
    """
    assert _feed(calibrator, homography_for()).ok
    calibrator.mark_cut()
    for _ in range(3):
        r = _feed(calibrator, homography_for((10.0, 4.0)))
        assert not r.ok, "yeniden yakalama kapalıyken kabul edilmemeli"
        assert "çapa" in r.reason


def test_cut_recovers_from_anchor_when_reacquire_is_on() -> None:
    """Yeniden yakalama açıkken ana kamera görüntüsüne dönünce toparlanmalı.

    TV yayınında ana kamera kesmeden sonra benzer kadraja döner; çapa hangi
    yarıya bakıldığını sabitlediği için 180° ikizliği de kapanır.
    """
    cal = PerFrameCalibrator(
        calibration_from_homography(homography_for(), (W, H)),
        image_size=(W, H), allow_reacquire=True,
    )
    assert _feed(cal, homography_for()).ok
    cal.mark_cut()
    assert not cal.tracking

    back = _feed(cal, homography_for((10.0, 4.0)))
    assert back.ok, back.reason
    assert cal.tracking


def test_cut_recovery_still_demands_a_strong_fit() -> None:
    """Kesme sonrası çıta YÜKSEK kalmalı — süreklilik desteği yok.

    Yeniden yakalamayı açmak "her şeyi kabul et" demek değildir: çapadan uzak
    bir sahne %85 inlier'ı tutturamaz ve reddedilir.
    """
    cal = PerFrameCalibrator(
        calibration_from_homography(homography_for(), (W, H)),
        image_size=(W, H), allow_reacquire=True,
    )
    assert _feed(cal, homography_for()).ok
    cal.mark_cut()
    far = _feed(cal, homography_for((300.0, 120.0)))
    assert not far.ok, far.reason
    assert not cal.tracking
