"""Engine sinyal/gürültü kalite sınıflandırması (Faz 9 #46).

Bir engine'in bir metrik serisinin (maç-takım örnekleri) gerçek SİNYAL mi
yoksa GÜRÜLTÜ mü ürettiğini sınıflandırır. Amaç: pilot-dışı ~69 engine'in
hangisinin sentetik testte güzel görünüp prod'da sabit/gürültü olduğunu
KANITLANABİLİR biçimde işaretlemek (bir tam sezon audit'inin karar mantığı).

`scripts/full_season_audit.py` içindeki gömülü heuristik buraya çıkarıldı:
saf + test edilebilir (StatsBomb verisi gerekmeden doğrulanır), tek kaynak.
Canlı-sinyal `engine.signal_quality`'den AYRI bir kaygı (o WebSocket ısınma
filtresi; bu offline engine-kalite denetimi).

Yöntem (saf istatistik):
- CV = stdev/|mean|: dağılımın göreli genişliği.
- team_spread: takım-arası ortalama farkı (engine takımları ayırt edebiliyor mu).
- mean ≈ 0 (zero-sum metrikler, örn. dominance) özel ele alınır → mutlak
  stdev/spread'e bakılır.

Verdict: DEAD / INSUFFICIENT_DATA / NO_SIGNAL / MODERATE / STRONG_SIGNAL.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

ENGINE_NAME = "engine.audit_quality"
ENGINE_VERSION = "1"

DEFAULT_MIN_SAMPLES = 20
# Eşikler — full_season_audit heuristic'inden çıkarıldı (tek kaynak).
_NO_SIGNAL_CV = 0.05
_NO_SIGNAL_SPREAD_RATIO = 0.10
_STRONG_CV = 0.30
_STRONG_SPREAD_RATIO = 0.30
_ZERO_MEAN_EPS = 1e-6
_ZERO_MEAN_STRONG_STDEV = 0.5
_ZERO_MEAN_STRONG_SPREAD = 1.0


@dataclass(frozen=True)
class SignalVerdict:
    verdict: str          # STRONG_SIGNAL / MODERATE / NO_SIGNAL / INSUFFICIENT_DATA / DEAD
    n_samples: int
    mean: float
    stdev: float
    cv: float             # inf → mean≈0
    team_spread: float
    n_teams: int


def classify_signal(
    samples: list[float],
    team_means: dict[int, float] | None = None,
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> SignalVerdict:
    """Bir engine metrik serisini sinyal/gürültü olarak sınıflandır.

    `samples`: tüm maç-takım metrik değerleri (tek engine, tek metrik).
    `team_means`: team_id → o takımın ortalaması (takım-arası ayrım için).
    """
    team_means = team_means or {}
    n = len(samples)
    if n == 0:
        return SignalVerdict("DEAD", 0, 0.0, 0.0, float("inf"), 0.0, 0)

    mean = statistics.mean(samples)
    stdev = statistics.pstdev(samples) if n > 1 else 0.0
    cv = (stdev / abs(mean)) if abs(mean) > _ZERO_MEAN_EPS else float("inf")
    team_spread = (
        (max(team_means.values()) - min(team_means.values()))
        if len(team_means) > 1 else 0.0
    )
    spread_ratio = (team_spread / abs(mean)) if abs(mean) > _ZERO_MEAN_EPS else 0.0

    if n < min_samples:
        verdict = "INSUFFICIENT_DATA"
    elif abs(mean) < _ZERO_MEAN_EPS:
        verdict = (
            "STRONG_SIGNAL"
            if stdev > _ZERO_MEAN_STRONG_STDEV or team_spread > _ZERO_MEAN_STRONG_SPREAD
            else "NO_SIGNAL"
        )
    elif cv < _NO_SIGNAL_CV and spread_ratio < _NO_SIGNAL_SPREAD_RATIO:
        verdict = "NO_SIGNAL"
    elif cv >= _STRONG_CV or spread_ratio >= _STRONG_SPREAD_RATIO:
        verdict = "STRONG_SIGNAL"
    else:
        verdict = "MODERATE"

    return SignalVerdict(
        verdict=verdict,
        n_samples=n,
        mean=round(mean, 4),
        stdev=round(stdev, 4),
        cv=round(cv, 4) if cv != float("inf") else float("inf"),
        team_spread=round(team_spread, 4),
        n_teams=len(team_means),
    )
