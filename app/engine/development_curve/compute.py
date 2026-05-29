"""Development Curve — uzun-dönem gelişim eğrisi + ileri projeksiyon (saf).

Bir oyuncunun/takımın zaman serisini (sezon-sezon ya da maç-maç metrik) alıp:
- eğim (least-squares linear regresyon) → yükseliş/düşüş/sabit,
- son dönem ortalaması, oynaklık (volatilite),
- bir sonraki adım için basit projeksiyon (son değer + eğim).

Sezon-içi momentum tahmini için de aynı: son N maç → bir sonraki maç beklentisi.
Saf: sayı serisi → rapor. `statistics` dışı bağımlılık yok.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

ENGINE_NAME = "engine.development_curve"
ENGINE_VERSION = "1"

# Eğim yön bandı: |slope| bunun altıysa "sabit".
SLOPE_FLAT_EPS = 0.02


@dataclass(frozen=True)
class DevelopmentReport:
    n: int
    slope: float                  # birim başına değişim (index ekseninde)
    direction: str                # "yükseliş" | "düşüş" | "sabit"
    recent_mean: float
    volatility: float             # regresyon kalıntılarının std'si
    projection_next: float        # bir sonraki adım tahmini


def _linreg(values: list[float]) -> tuple[float, float]:
    """(slope, intercept) — least squares, x = 0..n-1."""
    n = len(values)
    xs = list(range(n))
    mx = (n - 1) / 2.0
    my = statistics.fmean(values)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values, strict=False)) / denom
    intercept = my - slope * mx
    return slope, intercept


def development_curve(
    values: list[float],
    *,
    recent_window: int = 3,
) -> DevelopmentReport:
    n = len(values)
    if n == 0:
        return DevelopmentReport(0, 0.0, "sabit", 0.0, 0.0, 0.0)
    if n == 1:
        return DevelopmentReport(1, 0.0, "sabit", round(values[0], 3), 0.0,
                                 round(values[0], 3))

    slope, intercept = _linreg(values)
    direction = ("yükseliş" if slope > SLOPE_FLAT_EPS
                 else "düşüş" if slope < -SLOPE_FLAT_EPS else "sabit")

    # Kalıntı std → volatilite
    residuals = [v - (intercept + slope * i)
                 for i, v in enumerate(values)]
    volatility = statistics.pstdev(residuals) if n >= 2 else 0.0

    recent = values[-recent_window:]
    recent_mean = statistics.fmean(recent)
    # Projeksiyon: regresyon doğrusunun bir sonraki noktası
    projection = intercept + slope * n

    return DevelopmentReport(
        n=n, slope=round(slope, 4), direction=direction,
        recent_mean=round(recent_mean, 3), volatility=round(volatility, 3),
        projection_next=round(projection, 3),
    )
