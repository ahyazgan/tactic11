"""Performance Consistency — oyuncu rating serisi tutarlılığı.

Bir oyuncunun maç-maç rating'lerinden (veya başka tek-boyutlu KPI) çıkış:
  - mean, sd, cv (coefficient of variation = sd/|mean|)
  - best, worst, sample_count
  - consistency_label: high (CV < 0.10), medium (< 0.20), volatile (≥ 0.20)
  - z_recent_5: son 5 maçın mean → genel mean'e z-score (form yönü)
  - reliability_score 0..100: 100 = çok tutarlı + yüksek mean

Pure compute.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.performance_consistency"
ENGINE_VERSION = "1"

CV_HIGH = 0.10
CV_MEDIUM = 0.20


@dataclass(frozen=True)
class PerformanceSample:
    """Tek bir maçın KPI değeri (genellikle rating 0-10)."""
    match_id: int
    value: float
    minute_played: float = 90.0      # ağırlıklandırma için


@dataclass(frozen=True)
class ConsistencyReport:
    sample_count: int
    mean: float
    sd: float
    cv: float
    best: float
    worst: float
    consistency_label: str           # "high" | "medium" | "volatile" | "insufficient"
    z_recent_5: float                # son 5 oyunun z-score'u
    reliability_score: float         # 0..100
    summary: str                     # TR
    notes: tuple[str, ...] = field(default_factory=tuple)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sd(xs: list[float], mu: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _label_from_cv(cv: float, n: int) -> str:
    if n < 3:
        return "insufficient"
    if cv < CV_HIGH:
        return "high"
    if cv < CV_MEDIUM:
        return "medium"
    return "volatile"


def _reliability(mean: float, cv: float, n: int, max_value: float = 10.0) -> float:
    """0..100: yüksek mean + düşük CV → yüksek skor.

    Az örnekle düşük skor (n < 5 → ceza).
    """
    if n < 2:
        return 0.0
    mean_score = max(0.0, min(1.0, mean / max_value))     # 0..1
    cv_score = max(0.0, 1.0 - min(cv / 0.30, 1.0))         # 0..1 (cv 0=1, cv 0.30+=0)
    sample_factor = min(1.0, n / 8.0)                      # n=8+ → tam etki
    return round(100.0 * mean_score * cv_score * sample_factor, 1)


def compute_performance_consistency(
    samples: Iterable[PerformanceSample],
) -> EngineResult[ConsistencyReport]:
    slist = list(samples)
    notes: list[str] = []

    if not slist:
        return _empty(0, "Sample yok — tutarlılık hesaplanamadı")
    if len(slist) < 3:
        notes.append("Az örnek — tutarlılık yorumu sınırlı")

    values = [s.value for s in slist]
    mu = _mean(values)
    sd = _sd(values, mu)
    cv = (sd / abs(mu)) if mu != 0 else 0.0
    best = max(values)
    worst = min(values)
    label = _label_from_cv(cv, len(values))

    recent_5 = values[-5:]
    z_recent_5 = 0.0
    if sd > 0 and len(recent_5) >= 1:
        z_recent_5 = (_mean(recent_5) - mu) / sd

    reliability = _reliability(mu, cv, len(values))

    if label == "insufficient":
        summary = (
            f"{len(slist)} örnek — tutarlılık hesaplanamadı "
            f"(en az 3 maç gerek)"
        )
    else:
        summary = (
            f"Mean {mu:.2f} (sd {sd:.2f}, CV {cv:.2f}) — {label}; "
            f"son 5 z={z_recent_5:+.2f}"
        )

    report = ConsistencyReport(
        sample_count=len(slist),
        mean=round(mu, 3),
        sd=round(sd, 3),
        cv=round(cv, 3),
        best=round(best, 3),
        worst=round(worst, 3),
        consistency_label=label,
        z_recent_5=round(z_recent_5, 3),
        reliability_score=reliability,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=0,
        metric="performance_consistency",
        value={
            "sample_count": len(slist),
            "mean": round(mu, 3),
            "sd": round(sd, 3),
            "cv": round(cv, 3),
            "label": label,
            "reliability_score": reliability,
        },
        inputs={"thresholds": {"cv_high": CV_HIGH, "cv_medium": CV_MEDIUM}},
        formula=(
            "cv = sd/|mean|; label = high(<0.10)/medium(<0.20)/volatile(≥0.20); "
            "reliability = 100 * (mean/10) * (1 - cv/0.30) * min(n/8, 1)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[ConsistencyReport]:
    report = ConsistencyReport(
        sample_count=n,
        mean=0.0, sd=0.0, cv=0.0, best=0.0, worst=0.0,
        consistency_label="insufficient",
        z_recent_5=0.0,
        reliability_score=0.0,
        summary=msg,
        notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="performance_consistency",
        value={"sample_count": n, "label": "insufficient"},
        inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
