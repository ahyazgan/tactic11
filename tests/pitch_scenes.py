"""Sentetik yayın sahneleri — çapa/kalibrasyon testleri için ortak yardımcılar.

`homography_fit.anchor_candidates` kadrajın TAMAMINI sahanın bir parçasına eşler
(gerçek yayın kamerası sahanın bir bölümünü kadraja sığdırır, çevresinde boşluk
bırakmaz). Eski test sahneleri sahayı kadrajın İÇİNE koyuyordu; o yüzden çapa
arama hiçbir sentetik sahnede kabul edilmiyor ve kabul yolu yalnız gerçek
videoyla (bench) doğrulanabiliyordu. Buradaki sahneler aday uzayının içindedir:
kadraj = sahanın `view_len_m` genişliğinde, `centre_m` merkezli bir dilimi,
üst kenar `taper` oranında kısa (perspektif), `offset_px` kadar kaydırılmış.

cv2 gerekmez: mesafe haritası yinelemeli chamfer ile üretilir.
"""
from __future__ import annotations

import numpy as np

from app.tracking.calibration import dlt_homography
from app.tracking.homography_fit import project_to_image
from app.tracking.pitch_model import PITCH_WIDTH_M, model_points


def view_homography(
    width: int, height: int, *, centre_m: float = 52.5, view_len_m: float = 60.0,
    taper: float = 0.82, offset_px: tuple[float, float] = (0.0, 0.0),
    scale: float = 1.0,
) -> np.ndarray:
    """Kadraj → saha dilimi homografisi (görüntü → saha).

    Görüntünün ALTI yakın taç çizgisine (y = 68) eşlenir — TV kuralıyla aynı
    yönelim. `offset_px`/`scale` kadraj dörtgenini oynatır (kamera hareketi).
    """
    cx, half_top = width / 2.0, width / 2.0 * taper
    quad = np.array([
        [cx - half_top, 0.0], [cx + half_top, 0.0],
        [width, float(height)], [0.0, float(height)],
    ]) * scale + np.array(offset_px)
    x0, x1 = centre_m - view_len_m / 2.0, centre_m + view_len_m / 2.0
    pitch = np.array([[x0, 0.0], [x1, 0.0], [x1, PITCH_WIDTH_M], [x0, PITCH_WIDTH_M]])
    return dlt_homography(quad, pitch)


def dist_map_for(h: np.ndarray, width: int, height: int, *,
                 step_m: float = 0.2, iters: int = 40) -> np.ndarray:
    """Homografinin çizgilerinden mesafe haritası (yinelemeli chamfer, ±iters px)."""
    mask = np.zeros((height, width), dtype=bool)
    for u, v in project_to_image(h, model_points(step_m)):
        if not (np.isfinite(u) and np.isfinite(v)):
            continue
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < width and 0 <= vi < height:
            mask[max(0, vi - 1):vi + 2, max(0, ui - 1):ui + 2] = True
    far = float(iters + 10)
    d = np.where(mask, 0.0, far)
    for _ in range(iters):
        nxt = d
        for axis in (0, 1):
            for direction in (1, -1):
                shifted = np.roll(d, direction, axis=axis)
                # roll kenardan sarar; sarılan şeridi "uzak" say
                if axis == 0:
                    shifted[0 if direction == 1 else -1, :] = far
                else:
                    shifted[:, 0 if direction == 1 else -1] = far
                nxt = np.minimum(nxt, shifted + 1.0)
        if np.array_equal(nxt, d):
            break
        d = nxt
    return d


def line_pixels_of(dmap: np.ndarray) -> int:
    return int((dmap == 0.0).sum())
