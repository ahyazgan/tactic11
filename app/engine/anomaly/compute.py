"""Anomaly — metrik serisinde aykırı değer + form kırılması tespiti (saf).

İki tespit:
1. Nokta anomalisi: serideki bir değer genel ortalamadan z-skor eşiğini aşıyor
   (ani sıçrama/çöküş).
2. Form kırılması (change point): son pencere ortalaması ile önceki pencere
   ortalaması belirgin farklıysa → "form değişti" (yukarı/aşağı).

Saf: sayı serisi → rapor. `statistics` dışı bağımlılık yok.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

ENGINE_NAME = "engine.anomaly"
ENGINE_VERSION = "1"

# Nokta anomalisi z-skor eşiği.
Z_THRESHOLD = 2.0
# Form kırılması: pencere boyutu + iki pencere ortalama farkının stdev katı.
BREAK_WINDOW = 3
BREAK_SIGMA = 1.0


@dataclass(frozen=True)
class Anomaly:
    index: int
    value: float
    z_score: float
    direction: str                # "yüksek" | "düşük"


@dataclass(frozen=True)
class AnomalyReport:
    n: int
    mean: float
    stdev: float
    anomalies: tuple[Anomaly, ...] = field(default_factory=tuple)
    # Form kırılması
    break_detected: bool = False
    break_direction: str | None = None   # "yükseliş" | "düşüş"
    break_magnitude: float = 0.0


def detect_anomalies(
    series: list[float],
    *,
    z_threshold: float = Z_THRESHOLD,
    break_window: int = BREAK_WINDOW,
) -> AnomalyReport:
    n = len(series)
    if n < 2:
        return AnomalyReport(n=n, mean=round(series[0], 3) if series else 0.0,
                             stdev=0.0)
    mean = statistics.fmean(series)
    stdev = statistics.pstdev(series)

    anomalies: list[Anomaly] = []
    if stdev > 0:
        for i, v in enumerate(series):
            z = (v - mean) / stdev
            if abs(z) >= z_threshold:
                anomalies.append(Anomaly(
                    index=i, value=round(v, 3), z_score=round(z, 3),
                    direction="yüksek" if z > 0 else "düşük",
                ))

    # Form kırılması: son pencere vs önceki pencere
    break_detected = False
    break_direction: str | None = None
    break_mag = 0.0
    if n >= break_window * 2:
        recent = series[-break_window:]
        prior = series[-break_window * 2:-break_window]
        r_mean = statistics.fmean(recent)
        p_mean = statistics.fmean(prior)
        diff = r_mean - p_mean
        if stdev > 0 and abs(diff) >= BREAK_SIGMA * stdev:
            break_detected = True
            break_direction = "yükseliş" if diff > 0 else "düşüş"
            break_mag = round(diff, 3)

    return AnomalyReport(
        n=n, mean=round(mean, 3), stdev=round(stdev, 3),
        anomalies=tuple(anomalies),
        break_detected=break_detected, break_direction=break_direction,
        break_magnitude=break_mag,
    )
