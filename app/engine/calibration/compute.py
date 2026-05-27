"""Tahmin kalibrasyon metrikleri — saf hesap.

Girdi: (predicted_prob, actual_outcome) çiftleri.
Çıktı: CalibrationReport (Brier score, log loss, expected calibration error,
buckets).

Engine kuralı geçerli: DB/HTTP yok. Üst katman predictions tablosundan
okur, bu modülü çağırır.

Metrikler:
- **Brier score (multi-class)**: Σ(predicted_prob - one_hot)² ortalaması.
  0..2 arası; düşük = iyi. Mükemmel tahmin = 0.
- **Log loss (cross-entropy)**: -ln(P(actual)) ortalaması. 0..∞;
  düşük = iyi. Tahmin'in eps altı clipping ile sıfıra düşmesi önlenir.
- **Expected Calibration Error (ECE)**: olasılık aralıklarına böl, her
  bucket için |ortalama_predicted - gerçek_frekans|, sample ağırlıklı
  ortalama. Düşük = iyi kalibre.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.calibration"
ENGINE_VERSION = "1"

# Olasılık clipping — log loss'da 0'a düşmesini önler
_PROB_EPS = 1e-6
# ECE bucket sayısı
_BUCKET_COUNT = 10

OUTCOMES = ("home", "draw", "away")


@dataclass(frozen=True)
class CalibrationBucket:
    """Belirli bir olasılık aralığında gerçek frekans vs ortalama tahmin."""
    bucket_lower: float
    bucket_upper: float
    sample_count: int
    avg_predicted_prob: float  # bucket içindeki tahminlerin ortalaması
    actual_frequency: float  # bucket içinde gerçek olan olayın oranı


@dataclass(frozen=True)
class CalibrationReport:
    sample_count: int  # değerlendirilen tahmin sayısı
    brier_score: float | None
    log_loss: float | None
    expected_calibration_error: float | None
    home_outcome_buckets: list[CalibrationBucket]


def _clip(p: float) -> float:
    return max(_PROB_EPS, min(1.0 - _PROB_EPS, p))


def compute_calibration(
    samples: Iterable[tuple[float, float, float, str]],
    *,
    engine: str = "engine.predict",
    engine_version: str = "?",
) -> EngineResult[CalibrationReport]:
    """`samples`: (prob_home, prob_draw, prob_away, actual_outcome) çiftleri.

    `actual_outcome` ∈ {"home", "draw", "away"}.
    """
    items = list(samples)
    if not items:
        report = CalibrationReport(
            sample_count=0,
            brier_score=None,
            log_loss=None,
            expected_calibration_error=None,
            home_outcome_buckets=[],
        )
        audit = AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="engine_calibration",
            subject_id=0,
            metric="calibration_report",
            value=asdict(report),
            inputs={"target_engine": engine, "target_engine_version": engine_version},
            formula="N=0 → metrikler hesaplanmadı",
        )
        return EngineResult(value=report, audit=audit)

    n = len(items)
    brier_sum = 0.0
    ll_sum = 0.0
    home_probs_with_actual: list[tuple[float, bool]] = []

    for ph, pd, pa, actual in items:
        # Outcome one-hot
        oh_home = 1.0 if actual == "home" else 0.0
        oh_draw = 1.0 if actual == "draw" else 0.0
        oh_away = 1.0 if actual == "away" else 0.0
        # Brier (multi-class): Σ(p-y)² over outcomes
        brier_sum += (ph - oh_home) ** 2 + (pd - oh_draw) ** 2 + (pa - oh_away) ** 2
        # Log loss — actual sınıfın olasılığı
        if actual == "home":
            ll_sum += -math.log(_clip(ph))
        elif actual == "draw":
            ll_sum += -math.log(_clip(pd))
        else:
            ll_sum += -math.log(_clip(pa))
        # Home outcome buckets — predict accuracy en görünür kısım
        home_probs_with_actual.append((ph, actual == "home"))

    brier = brier_sum / n
    ll = ll_sum / n

    # ECE: prob_home_win aralıklarına böl; her bucket için avg(pred) vs
    # actual home oranı; mutlak fark sample-weighted ortalama
    buckets = _build_buckets(home_probs_with_actual)
    weighted_diff = 0.0
    total = 0
    for b in buckets:
        if b.sample_count == 0:
            continue
        total += b.sample_count
        weighted_diff += b.sample_count * abs(b.avg_predicted_prob - b.actual_frequency)
    ece = weighted_diff / total if total > 0 else 0.0

    report = CalibrationReport(
        sample_count=n,
        brier_score=round(brier, 4),
        log_loss=round(ll, 4),
        expected_calibration_error=round(ece, 4),
        home_outcome_buckets=buckets,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="engine_calibration",
        subject_id=0,
        metric="calibration_report",
        value=asdict(report),
        inputs={
            "target_engine": engine,
            "target_engine_version": engine_version,
            "sample_count": n,
            "bucket_count": _BUCKET_COUNT,
        },
        formula=(
            "Brier = Σ(p-y)² / N (multi-class); "
            "log_loss = -ln(P(actual)) ortalaması (clipped at 1e-6); "
            f"ECE = sample-weighted |avg_pred - actual_freq|, {_BUCKET_COUNT} bucket"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _build_buckets(items: list[tuple[float, bool]]) -> list[CalibrationBucket]:
    """home_prob → eşit-genişlikli 10 bucket; her bucket için freq."""
    bucket_size = 1.0 / _BUCKET_COUNT
    bucket_items: list[list[tuple[float, bool]]] = [[] for _ in range(_BUCKET_COUNT)]
    for prob, actual in items:
        # 1.0 dahil son bucket'a düşsün.
        # Float kayması (0.7/0.1 → 6.999...) için küçük epsilon ekle.
        idx = min(int(prob / bucket_size + 1e-9), _BUCKET_COUNT - 1)
        bucket_items[idx].append((prob, actual))
    out: list[CalibrationBucket] = []
    for i, contents in enumerate(bucket_items):
        lower = i * bucket_size
        upper = (i + 1) * bucket_size
        n = len(contents)
        if n == 0:
            out.append(CalibrationBucket(
                bucket_lower=round(lower, 2), bucket_upper=round(upper, 2),
                sample_count=0, avg_predicted_prob=0.0, actual_frequency=0.0,
            ))
            continue
        avg_p = sum(p for p, _ in contents) / n
        actual_freq = sum(1 for _, a in contents if a) / n
        out.append(CalibrationBucket(
            bucket_lower=round(lower, 2), bucket_upper=round(upper, 2),
            sample_count=n,
            avg_predicted_prob=round(avg_p, 4),
            actual_frequency=round(actual_freq, 4),
        ))
    return out
