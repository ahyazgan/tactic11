"""Kalibrasyon düzeltici — temperature scaling (saf hesap).

`compute.py` kalibrasyonu ÖLÇER (Brier/log-loss/ECE); bu modül DÜZELTİR.
Ham olasılıkları geçmiş (tahmin, gerçek) verisinden öğrenilen tek bir
sıcaklık T ile dürüstleştirir:

    p_i' = p_i^(1/T) / Σ_j p_j^(1/T)

Bu, klasik temperature scaling'in olasılık-uzayı biçimidir: olasılıklar
softmax(z) olduğundan p^(1/T) normalize = softmax(z/T). T>1 → tahmini
yumuşatır (aşırı-güveni kırar), T<1 → keskinleştirir, T=1 → kimlik
(değiştirmez). Aşırı-güvenli bir motor (söylediği %90 gerçekte %70 çıkıyor)
T>1 ile düzelir ve log-loss düşer.

T tek parametre → küçük örneklemde bile sağlam (overfit etmez). 1B ızgara
aramasıyla log-loss minimize edilir; sklearn gerektirmez.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

# log-loss'da olasılığın 0'a düşmesini önler (clip).
_PROB_EPS = 1e-9
# Sıcaklık arama aralığı + ızgara.
_T_MIN = 0.5
_T_MAX = 5.0
_COARSE_STEP = 0.1
_FINE_STEP = 0.01

OUTCOMES = ("home", "draw", "away")


@dataclass(frozen=True)
class Calibrator:
    """Öğrenilmiş kalibrasyon dönüşümü."""
    method: str  # "temperature"
    temperature: float  # T; 1.0 → kimlik (düzeltme yok)
    n_train: int
    log_loss_before: float  # T=1 (ham) log-loss
    log_loss_after: float  # öğrenilen T ile log-loss

    @property
    def improved(self) -> bool:
        """Düzeltme ham haline göre ölçülebilir iyileşme sağladı mı."""
        return self.log_loss_after < self.log_loss_before - 1e-6


def apply_temperature(
    probs: tuple[float, float, float], temperature: float
) -> tuple[float, float, float]:
    """(p_home, p_draw, p_away) → sıcaklık-ölçeklenmiş, yeniden normalize.

    T<=0 güvenliği: kimlik. Çıktı toplamı 1.0.
    """
    t = temperature if temperature and temperature > 0 else 1.0
    inv = 1.0 / t
    powered = [max(p, _PROB_EPS) ** inv for p in probs]
    s = sum(powered)
    if s <= 0:
        return probs
    return (powered[0] / s, powered[1] / s, powered[2] / s)


def _mean_log_loss(
    items: list[tuple[float, float, float, str]], temperature: float
) -> float:
    """Sıcaklık uygulandıktan sonra ortalama çok-sınıflı log-loss."""
    total = 0.0
    for ph, pd, pa, actual in items:
        cp = apply_temperature((ph, pd, pa), temperature)
        idx = OUTCOMES.index(actual) if actual in OUTCOMES else 0
        total += -math.log(max(cp[idx], _PROB_EPS))
    return total / len(items)


def fit_temperature(
    samples: Iterable[tuple[float, float, float, str]],
) -> Calibrator:
    """(prob_home, prob_draw, prob_away, actual) → log-loss'u minimize eden T.

    Boş örneklem → kimlik kalibratör (T=1). Önce kaba (0.1) sonra ince (0.01)
    ızgara araması; tepe noktası etrafında rafine eder.
    """
    items = [s for s in samples if s[3] in OUTCOMES]
    if not items:
        return Calibrator(
            method="temperature", temperature=1.0, n_train=0,
            log_loss_before=0.0, log_loss_after=0.0,
        )

    baseline = _mean_log_loss(items, 1.0)

    # Kaba ızgara.
    best_t, best_ll = 1.0, baseline
    steps = int(round((_T_MAX - _T_MIN) / _COARSE_STEP)) + 1
    for i in range(steps):
        t = _T_MIN + i * _COARSE_STEP
        ll = _mean_log_loss(items, t)
        if ll < best_ll:
            best_t, best_ll = t, ll

    # İnce ızgara — kaba en iyinin ±_COARSE_STEP komşuluğu.
    lo = max(_T_MIN, best_t - _COARSE_STEP)
    hi = min(_T_MAX, best_t + _COARSE_STEP)
    fine_steps = int(round((hi - lo) / _FINE_STEP)) + 1
    for i in range(fine_steps):
        t = lo + i * _FINE_STEP
        ll = _mean_log_loss(items, t)
        if ll < best_ll:
            best_t, best_ll = t, ll

    return Calibrator(
        method="temperature",
        temperature=round(best_t, 3),
        n_train=len(items),
        log_loss_before=round(baseline, 4),
        log_loss_after=round(best_ll, 4),
    )
