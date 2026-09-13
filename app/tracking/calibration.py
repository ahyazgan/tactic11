"""Saha kalibrasyonu — görüntü pikseli ↔ saha koordinatı homografisi.

Sabit kamera (kulüp taktik kamerası, drone, panoramik) için bir kez
yapılır: en az 4 saha işaret noktasının piksel konumu ve gerçek saha
koordinatı (metre) eşlenir; DLT ile 3×3 homografi çıkar.

Saha koordinat sistemi (metre): orijin sol-üst köşe, x boyuna 0..105 (sağa
hücum), y enine 0..68 (aşağı). Domain'e geçerken 0-100 normalize edilir —
StatsBomb 360 adapter'ıyla aynı çerçeve, overlay aynı kalır.

Kalibrasyon JSON:
{
  "image_size": [3840, 2160],
  "pitch_length_m": 105, "pitch_width_m": 68,
  "points": [
    {"image": [412, 388], "pitch": [0, 0], "label": "sol üst köşe"},
    ...
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


class CalibrationError(ValueError):
    """Eksik/tutarsız kalibrasyon noktası."""


def _normalize_points(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley normalizasyonu — DLT'nin sayısal kararlılığı için."""
    mean = pts.mean(axis=0)
    centered = pts - mean
    scale = np.sqrt(2.0) / max(np.sqrt((centered ** 2).sum(axis=1)).mean(), 1e-9)
    T = np.array([[scale, 0, -scale * mean[0]], [0, scale, -scale * mean[1]], [0, 0, 1.0]])
    homog = np.hstack([pts, np.ones((len(pts), 1))])
    return (T @ homog.T).T, T


TPS_MIN_POINTS = 8


def _tps_kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    r2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    return np.where(r2 > 0, r2 * np.log(np.sqrt(r2) + 1e-12), 0.0)


def tps_fit(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """İnce-levha spline: src (n,2) → dst (n,2), kontrol noktalarını tam geçer.

    Çekirdek U(r) = r²·log r + afin terim; (n+3)×(n+3) doğrusal sistem. Küçük n
    (onlarca nokta) için kütüphane gerekmez; sonuç deterministik ve şeffaftır.
    """
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    n = len(src)
    if n < TPS_MIN_POINTS or src.shape != dst.shape:
        raise CalibrationError(f"tps için en az {TPS_MIN_POINTS} eşleşmiş nokta gerekli")
    k = _tps_kernel(src, src)
    p = np.hstack([np.ones((n, 1)), src])
    a = np.zeros((n + 3, n + 3))
    a[:n, :n] = k
    a[:n, n:] = p
    a[n:, :n] = p.T
    b = np.zeros((n + 3, 2))
    b[:n] = dst
    try:
        w = np.linalg.solve(a, b)
    except np.linalg.LinAlgError as e:
        raise CalibrationError("tps sistemi tekil — noktalar çakışık") from e
    return src, w


def tps_apply(model: tuple[np.ndarray, np.ndarray], q: np.ndarray) -> np.ndarray:
    src, w = model
    q = np.atleast_2d(np.asarray(q, dtype=float))
    u = _tps_kernel(q, src)
    return u @ w[:len(src)] + np.hstack([np.ones((len(q), 1)), q]) @ w[len(src):]


def _fit_residual_tps(src: np.ndarray, dst: np.ndarray, h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    base = np.array([apply_homography(h, float(u), float(v)) for u, v in src])
    return tps_fit(src, np.asarray(dst, dtype=float) - base)


def _apply_residual_tps(h: np.ndarray, model: tuple[np.ndarray, np.ndarray], q: np.ndarray) -> np.ndarray:
    q = np.atleast_2d(np.asarray(q, dtype=float))
    base = np.array([apply_homography(h, float(u), float(v)) for u, v in q])
    return base + tps_apply(model, q)


def dlt_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """src (n,2) → dst (n,2) homografisi (n ≥ 4). Dönen H: dst ~ H·src."""
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 2 or len(src) < 4:
        raise CalibrationError("en az 4 (u,v)↔(x,y) nokta çifti gerekli")
    s, Ts = _normalize_points(src)
    d, Td = _normalize_points(dst)
    rows = []
    for (x, y, _), (X, Y, _) in zip(s, d, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, X * x, X * y, X])
        rows.append([0, 0, 0, -x, -y, -1, Y * x, Y * y, Y])
    A = np.asarray(rows)
    _, sing, vt = np.linalg.svd(A)
    if sing[-2] < 1e-12:
        raise CalibrationError("noktalar dejenere (doğrusal/çakışık) — homografi belirsiz")
    Hn = vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    return H / H[2, 2]


def apply_homography(H: np.ndarray, u: float, v: float) -> tuple[float, float]:
    p = H @ np.array([u, v, 1.0])
    if abs(p[2]) < 1e-12:
        return float("nan"), float("nan")
    return float(p[0] / p[2]), float(p[1] / p[2])


@dataclass(frozen=True)
class CalibrationPoint:
    image: tuple[float, float]
    pitch: tuple[float, float]
    label: str = ""


@dataclass(frozen=True)
class PitchCalibration:
    points: tuple[CalibrationPoint, ...]
    image_size: tuple[int, int]
    pitch_length_m: float = PITCH_LENGTH_M
    pitch_width_m: float = PITCH_WIDTH_M
    meta: dict[str, Any] = field(default_factory=dict)
    # "homography": tek düzlem homografisi (varsayılan; drone/sabit dar açı).
    # "tps": homografi + ince-levha spline ARTIK düzeltmesi — panoramik/balıkgözü
    # sabit kamera gibi tek homografinin oturmadığı görüntüler için. Ölçüldü
    # (SoccerTrack v2 panoraması, 65 nokta, leave-one-out): yalnız homografi
    # 10.1 m, saf TPS 2.35 m (iç bölgede salınıyor, taç ötesine taşıyor),
    # homografi+TPS artık 1.76 m / medyan 1.18 m ve iç bölgede monoton.
    # Homografi perspektifi (1/w) taşır, TPS yalnız küçük ve düzgün kalanı.
    method: str = "homography"

    def __post_init__(self) -> None:
        if len(self.points) < 4:
            raise CalibrationError("en az 4 kalibrasyon noktası gerekli")
        if self.image_size[0] <= 0 or self.image_size[1] <= 0:
            raise CalibrationError("image_size pozitif olmalı")
        if self.method not in ("homography", "tps"):
            raise CalibrationError(f"bilinmeyen kalibrasyon yöntemi: {self.method}")
        if self.method == "tps" and len(self.points) < TPS_MIN_POINTS:
            raise CalibrationError(f"tps için en az {TPS_MIN_POINTS} nokta gerekli")

    @cached_property
    def homography(self) -> np.ndarray:
        src = np.array([p.image for p in self.points])
        dst = np.array([p.pitch for p in self.points])
        return dlt_homography(src, dst)

    @cached_property
    def _tps(self) -> tuple[np.ndarray, np.ndarray]:
        """Homografi artıklarının (saha m) TPS modeli."""
        src = np.array([p.image for p in self.points])
        dst = np.array([p.pitch for p in self.points])
        return _fit_residual_tps(src, dst, self.homography)

    @cached_property
    def reprojection_error_m(self) -> float:
        """Kalibrasyon noktalarının ortalama hatası (m).

        Homografi: geri-izdüşüm. TPS kontrol noktalarını tam geçer (hata 0 olurdu,
        anlamsız); onun yerine LEAVE-ONE-OUT hatası verilir — her nokta modelden
        çıkarılıp geri kalanla tahmin edilir. Saha içinde beklenen hatanın dürüst
        (kötümser) ölçüsüdür.
        """
        src = np.array([p.image for p in self.points])
        dst = np.array([p.pitch for p in self.points])
        if self.method == "tps":
            errs = []
            for i in range(len(src)):
                idx = [j for j in range(len(src)) if j != i]
                h = dlt_homography(src[idx], dst[idx])
                model = _fit_residual_tps(src[idx], dst[idx], h)
                pred = _apply_residual_tps(h, model, src[i:i + 1])[0]
                errs.append(float(np.hypot(*(pred - dst[i]))))
            return float(np.mean(errs))
        errs = []
        for p in self.points:
            x, y = apply_homography(self.homography, *p.image)
            errs.append(float(np.hypot(x - p.pitch[0], y - p.pitch[1])))
        return float(np.mean(errs))

    def image_to_pitch_m(self, u: float, v: float) -> tuple[float, float]:
        if self.method == "tps":
            x, y = _apply_residual_tps(self.homography, self._tps, np.array([[u, v]], dtype=float))[0]
            return float(x), float(y)
        return apply_homography(self.homography, u, v)

    def image_to_normalized(self, u: float, v: float, *, clamp: bool = True) -> tuple[float, float]:
        x_m, y_m = self.image_to_pitch_m(u, v)
        x = x_m / self.pitch_length_m * 100.0
        y = y_m / self.pitch_width_m * 100.0
        if clamp:
            x = min(100.0, max(0.0, x))
            y = min(100.0, max(0.0, y))
        return round(x, 3), round(y, 3)

    def is_on_pitch(self, u: float, v: float, margin_m: float = 2.0) -> bool:
        x_m, y_m = self.image_to_pitch_m(u, v)
        return (
            -margin_m <= x_m <= self.pitch_length_m + margin_m
            and -margin_m <= y_m <= self.pitch_width_m + margin_m
        )

    def visible_area_normalized(self) -> tuple[tuple[float, float], ...]:
        """Görüntü köşelerinin saha izdüşümü (kamera görüş alanı), 0-100 clamp."""
        w, h = self.image_size
        corners = [(0, 0), (w, 0), (w, h), (0, h)]
        return tuple(self.image_to_normalized(u, v) for u, v in corners)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_size": list(self.image_size),
            "pitch_length_m": self.pitch_length_m,
            "pitch_width_m": self.pitch_width_m,
            "method": self.method,
            "points": [
                {"image": list(p.image), "pitch": list(p.pitch), "label": p.label}
                for p in self.points
            ],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PitchCalibration:
        pts = tuple(
            CalibrationPoint(
                image=(float(p["image"][0]), float(p["image"][1])),
                pitch=(float(p["pitch"][0]), float(p["pitch"][1])),
                label=str(p.get("label", "")),
            )
            for p in d.get("points", [])
        )
        size = d.get("image_size") or [0, 0]
        return cls(
            points=pts,
            image_size=(int(size[0]), int(size[1])),
            pitch_length_m=float(d.get("pitch_length_m", PITCH_LENGTH_M)),
            pitch_width_m=float(d.get("pitch_width_m", PITCH_WIDTH_M)),
            meta=dict(d.get("meta") or {}),
            method=str(d.get("method") or "homography"),
        )

    @classmethod
    def load(cls, path: str | Path) -> PitchCalibration:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
