"""Kare başına kalibrasyon: homografiyi saha çizgilerine oturtma.

Sınav şu: bilinen bir homografiden sentetik çizgi görüntüsü üret, homografiyi
BOZ, sonra oturtmanın gerçeğe geri yakınsayıp yakınsamadığına bak. Kamera bir
karede bu kadar oynar; yayında yapılacak iş tam olarak budur.

cv2 gerekmez — mesafe haritası numpy ile üretilir (testler ana venv'de koşar).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.calibration import dlt_homography
from app.tracking.homography_fit import (
    corners_from_homography,
    project_to_image,
    refine_homography,
    score_homography,
)
from app.tracking.pitch_model import model_points, pitch_corners

W, H = 960, 540

# Gerçek kamera: sahayı perspektifle gören bir görüntü (köşeler piksel)
TRUE_CORNERS = np.array(
    [[120.0, 150.0], [840.0, 150.0], [930.0, 470.0], [30.0, 470.0]], dtype=float,
)


def true_homography() -> np.ndarray:
    return dlt_homography(TRUE_CORNERS, pitch_corners())


def line_mask_from(h_img_to_pitch: np.ndarray, *, thickness: int = 2) -> np.ndarray:
    """Modeli izdüşürüp çizgi piksellerini işaretle (sentetik "tespit edilmiş çizgiler")."""
    mask = np.zeros((H, W), dtype=bool)
    uv = project_to_image(h_img_to_pitch, model_points(0.25))
    for u, v in uv:
        if not (np.isfinite(u) and np.isfinite(v)):
            continue
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < W and 0 <= vi < H:
            lo_v, hi_v = max(0, vi - thickness), min(H, vi + thickness + 1)
            lo_u, hi_u = max(0, ui - thickness), min(W, ui + thickness + 1)
            mask[lo_v:hi_v, lo_u:hi_u] = True
    return mask


def distance_map(mask: np.ndarray, *, cap: float = 60.0) -> np.ndarray:
    """Her piksel → en yakın çizgi pikseline uzaklık (kaba ama yeterli, cv2'siz).

    İki geçişli chamfer yaklaşımı: doğru mesafe dönüşümüne çok yakın, testler
    için fazlasıyla yeterli. Üretimde cv2.distanceTransform kullanılır.
    """
    d = np.where(mask, 0.0, cap)
    for _ in range(2):
        for axis in (0, 1):
            for direction in (1, -1):
                shifted = np.roll(d, direction, axis=axis)
                if direction == 1:
                    if axis == 0:
                        shifted[0, :] = cap
                    else:
                        shifted[:, 0] = cap
                else:
                    if axis == 0:
                        shifted[-1, :] = cap
                    else:
                        shifted[:, -1] = cap
                d = np.minimum(d, shifted + 1.0)
    return d


@pytest.fixture(scope="module")
def truth():
    h = true_homography()
    return h, distance_map(line_mask_from(h))


def test_perfect_homography_scores_high(truth) -> None:
    h, dmap = truth
    score, inlier, visible = score_homography(h, dmap)
    assert inlier > 0.95, inlier
    assert score > 0.7
    assert visible > 200


def test_wrong_homography_scores_low(truth) -> None:
    """Kaymış homografi düşük puan almalı — yoksa skor hiçbir şey ayırt etmez."""
    _h, dmap = truth
    shifted = dlt_homography(TRUE_CORNERS + np.array([70.0, 40.0]), pitch_corners())
    _score, inlier, _visible = score_homography(shifted, dmap)
    assert inlier < 0.4, inlier


def test_refine_recovers_a_panned_camera(truth) -> None:
    """Asıl senaryo: kamera kaydı (25 px) → oturtma gerçeğe geri dönmeli."""
    h_true, dmap = truth
    drifted = dlt_homography(TRUE_CORNERS + np.array([25.0, 12.0]), pitch_corners())
    before = score_homography(drifted, dmap)[1]
    res = refine_homography(drifted, dmap)
    assert res.accepted, res.note
    assert res.inlier_ratio > before
    assert res.inlier_ratio > 0.9, res.inlier_ratio

    # Köşeler gerçeğe yakınsadı mı (piksel cinsinden)
    recovered = corners_from_homography(res.homography)
    err = float(np.abs(recovered - TRUE_CORNERS).max())
    assert err < 6.0, f"köşe hatası {err:.1f} px"

    # Asıl mesele: saha konumu doğru mu — bozuk homografi ile kıyasla
    probe_px = np.array([[480.0, 300.0]])
    def to_pitch(h):
        hom = np.hstack([probe_px, [[1.0]]]) @ h.T
        return hom[0, :2] / hom[0, 2]
    err_m_before = float(np.hypot(*(to_pitch(drifted) - to_pitch(h_true))))
    err_m_after = float(np.hypot(*(to_pitch(res.homography) - to_pitch(h_true))))
    assert err_m_before > 1.0, err_m_before
    assert err_m_after < 0.5, f"düzeltme sonrası {err_m_after:.2f} m"


def test_refine_recovers_zoom(truth) -> None:
    """Zoom da homografiyi bozar (köşeler içe/dışa gider)."""
    _h, dmap = truth
    centre = TRUE_CORNERS.mean(axis=0)
    zoomed = dlt_homography(centre + (TRUE_CORNERS - centre) * 1.08, pitch_corners())
    res = refine_homography(zoomed, dmap)
    assert res.accepted, res.note
    assert res.inlier_ratio > 0.9


def test_bad_start_is_refused_not_faked(truth) -> None:
    """Çok uzaktan başlarsa oturtma başarısız olmalı ve BUNU SÖYLEMELİ.

    Sessizce kötü bir homografi döndürmek, sahte konum üretmek demektir.
    """
    _h, dmap = truth
    hopeless = dlt_homography(TRUE_CORNERS + np.array([420.0, 260.0]), pitch_corners())
    res = refine_homography(hopeless, dmap, step_px=6.0)
    assert not res.accepted
    assert "atlanmalı" in res.note


def test_partial_view_is_refused_when_too_few_points(truth) -> None:
    """Yayında sahanın azı görünür; doğrulanamayacak kadar az nokta varsa reddet."""
    _h, dmap = truth
    tiny = np.zeros_like(dmap) + 60.0
    tiny[260:280, 460:500] = 0.0        # ufak bir çizgi parçası
    res = refine_homography(true_homography(), tiny)
    assert not res.accepted
    assert "atlanmalı" in res.note
