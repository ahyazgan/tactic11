"""PitchCalibration method="tps" — panoramik/balıkgözü sabit kamera için ince-levha spline.

Kilitlenen davranış: kontrol noktaları tam geçilir; `reprojection_error_m` TPS'te
leave-one-out hatasıdır (0 değil); homografi hâlâ hesaplanır; JSON'da `method`
korunur; az noktayla ya da bilinmeyen yöntemle tps reddedilir.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.calibration import CalibrationError, CalibrationPoint, PitchCalibration


def _warp(x: float, y: float) -> tuple[float, float]:
    """Doğrusal olmayan (balıkgözü benzeri) saha → görüntü eşlemesi."""
    u = 200 + 30 * x + 0.02 * (x - 52.5) ** 2 + 2.0 * y
    v = 150 + 12 * y + 0.01 * (y - 34) ** 2 + 0.5 * x
    return u, v


def _warped_grid(nx: int = 6, ny: int = 4) -> list[CalibrationPoint]:
    pts = []
    for i in range(nx):
        for j in range(ny):
            x, y = 105 * i / (nx - 1), 68 * j / (ny - 1)
            pts.append(CalibrationPoint(image=_warp(x, y), pitch=(x, y)))
    return pts


def test_tps_passes_control_points_and_beats_homography_between_them() -> None:
    pts = _warped_grid()
    tps = PitchCalibration(points=tuple(pts), image_size=(4000, 1200), method="tps")
    hom = PitchCalibration(points=tuple(pts), image_size=(4000, 1200))
    for p in pts:
        x, y = tps.image_to_pitch_m(*p.image)
        assert abs(x - p.pitch[0]) < 1e-6 and abs(y - p.pitch[1]) < 1e-6
    x0, y0 = 40.0, 20.0
    u, v = _warp(x0, y0)
    e_tps = np.hypot(*(np.array(tps.image_to_pitch_m(u, v)) - (x0, y0)))
    e_hom = np.hypot(*(np.array(hom.image_to_pitch_m(u, v)) - (x0, y0)))
    assert e_tps < 0.5 and e_tps < e_hom
    assert tps.homography.shape == (3, 3)          # çizim için kaba homografi hâlâ var


def test_tps_error_is_leave_one_out_not_zero() -> None:
    tps = PitchCalibration(points=tuple(_warped_grid()), image_size=(4000, 1200), method="tps")
    assert 0.0 < tps.reprojection_error_m < 2.0


def test_tps_roundtrip_json_and_min_points() -> None:
    tps = PitchCalibration(points=tuple(_warped_grid()), image_size=(4000, 1200), method="tps")
    again = PitchCalibration.from_dict(tps.to_dict())
    assert again.method == "tps"
    d = tps.to_dict()
    d.pop("method")
    assert PitchCalibration.from_dict(d).method == "homography"    # eski JSON'lar homografi
    with pytest.raises(CalibrationError):
        PitchCalibration(points=tuple(_warped_grid()[:5]), image_size=(10, 10), method="tps")
    with pytest.raises(CalibrationError):
        PitchCalibration(points=tuple(_warped_grid()), image_size=(10, 10), method="spline")
