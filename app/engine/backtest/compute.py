"""Backtest — olasılıksal motor çıktısını geçmiş sonuçlarda değerlendirme (saf).

Yeni bir tahmin motorunu (predict, sub-success vb.) geçmiş sezonda test etmek
için genel harness: (tahmin_olasılığı, gerçekleşti_mi) çiftleri → isabet oranı,
Brier skoru ve kalibrasyon binleri. Kalibrasyon = "%70 dediğinde gerçekten %70
mi çıkıyor". Bu, confidence/historical_hit_rate'i besler.

Saf: örnek listesi → metrikler. DB/zaman yok (caller geçmiş veriyi toplar).
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_NAME = "engine.backtest"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_rate: float          # bu bindeki gerçekleşme oranı


@dataclass(frozen=True)
class BacktestReport:
    n: int
    hit_rate: float               # (pred>=threshold) == actual oranı
    brier_score: float            # mean((pred-actual)^2), düşük = iyi
    mean_predicted: float
    observed_rate: float
    calibration: tuple[CalibrationBin, ...] = field(default_factory=tuple)
    well_calibrated: bool = False  # tüm binlerde |pred-observed| <= tolerance


# Bir bin "iyi kalibre" sayılır: tahmin ile gözlenen oran farkı <= bu.
CALIBRATION_TOLERANCE = 0.15


def backtest(
    samples: list[tuple[float, bool]],
    *,
    decision_threshold: float = 0.5,
    n_bins: int = 5,
) -> BacktestReport:
    """samples: [(predicted_prob 0..1, actual_outcome bool), ...]."""
    if not samples:
        return BacktestReport(
            n=0, hit_rate=0.0, brier_score=0.0,
            mean_predicted=0.0, observed_rate=0.0,
        )
    n = len(samples)
    hits = sum(1 for p, a in samples if (p >= decision_threshold) == a)
    hit_rate = round(hits / n, 3)
    brier = round(sum((p - (1.0 if a else 0.0)) ** 2 for p, a in samples) / n, 4)
    mean_pred = round(sum(p for p, _ in samples) / n, 3)
    observed = round(sum(1 for _, a in samples if a) / n, 3)

    # Kalibrasyon binleri (eşit genişlikli 0..1)
    width = 1.0 / n_bins
    bins: list[CalibrationBin] = []
    well = True
    for i in range(n_bins):
        lo = i * width
        hi = (i + 1) * width if i < n_bins - 1 else 1.0 + 1e-9
        members = [(p, a) for p, a in samples if lo <= p < hi]
        if not members:
            continue
        bn = len(members)
        mp = sum(p for p, _ in members) / bn
        obs = sum(1 for _, a in members if a) / bn
        if abs(mp - obs) > CALIBRATION_TOLERANCE:
            well = False
        bins.append(CalibrationBin(
            lower=round(lo, 3), upper=round(min(hi, 1.0), 3), n=bn,
            mean_predicted=round(mp, 3), observed_rate=round(obs, 3),
        ))

    return BacktestReport(
        n=n, hit_rate=hit_rate, brier_score=brier,
        mean_predicted=mean_pred, observed_rate=observed,
        calibration=tuple(bins), well_calibrated=well,
    )
