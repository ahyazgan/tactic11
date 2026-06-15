"""Performance Anomaly Detector — sakatlık/fatigue erken uyarı.

PerformancePoint dizisi (rating + minute_played + opt. fatigue_proxy) →
3 farklı anomali tipi:

  - sudden_drop          : son maç |rating - baseline_mean| ≥ k·sd
                            (k default 1.5)
  - extended_decline     : son 3 maçın hepsi baseline_mean'den < 1·sd düşük
  - minutes_drop         : son maç minute_played, baseline ort. dk'nın
                            %40'ından az (rotation/fitness sinyali)
  - consistency_collapse : son 5 maçın CV önceki tüm pencere CV'sinin
                            2× üstüne çıktı (yüksek volatilite belirdi)
  - fatigue_buildup      : opt. fatigue_proxy serisinin son 3'ünün ortalaması
                            tüm serinin ortalamasından 0.20 üstünde

Her event: type, minute_seen, severity (low/medium/high), z_or_factor,
rationale (TR), recommended_action (TR), confidence (0..1).

Pure compute. Tek input liste.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.performance_anomaly"
ENGINE_VERSION = "1"

DEFAULT_K_SD = 1.5
DEFAULT_DECLINE_WINDOW = 3
DEFAULT_DECLINE_SD = 1.0
MINUTES_DROP_RATIO = 0.40
CONSISTENCY_COLLAPSE_FACTOR = 2.0
FATIGUE_BUILDUP_DELTA = 0.20
MIN_BASELINE_SAMPLES = 5


@dataclass(frozen=True)
class PerformancePoint:
    match_id: int
    rating: float
    minute_played: float = 90.0
    fatigue_proxy: float | None = None     # 0..1 (1=exhausted), optional


@dataclass(frozen=True)
class AnomalyEvent:
    type: str
    match_id_seen: int                     # event'in tespit edildiği match
    severity: str                          # low | medium | high
    z_or_factor: float                     # tip-specific sayısal değer
    rationale: str                         # TR
    recommended_action: str                # TR
    confidence: float                      # 0..1


@dataclass(frozen=True)
class AnomalyReport:
    sample_count: int
    baseline_mean: float
    baseline_sd: float
    events: tuple[AnomalyEvent, ...]
    summary: str                           # TR 1-cümle
    overall_risk: str                      # low | medium | high (max event severity)
    notes: tuple[str, ...] = field(default_factory=tuple)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sd(xs: list[float], mu: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _severity(z: float, k_low: float = 1.5, k_high: float = 2.5) -> str:
    a = abs(z)
    if a >= k_high:
        return "high"
    if a >= k_low:
        return "medium"
    return "low"


def _detect_sudden_drop(
    points: list[PerformancePoint], k: float,
) -> AnomalyEvent | None:
    """Baseline = son maç hariç önceki tüm maçlar."""
    if len(points) < 2:
        return None
    prior_ratings = [p.rating for p in points[:-1]]
    if len(prior_ratings) < 2:
        return None
    prior_mean = _mean(prior_ratings)
    prior_sd = _sd(prior_ratings, prior_mean)
    if prior_sd <= 0:
        return None
    last = points[-1]
    z = (last.rating - prior_mean) / prior_sd
    if -z < k:    # son maç prior_mean'den k·sd kadar AŞAĞIDA değilse
        return None
    severity = _severity(z, k, k * 1.7)
    return AnomalyEvent(
        type="sudden_drop",
        match_id_seen=last.match_id,
        severity=severity,
        z_or_factor=round(z, 2),
        rationale=(
            f"Son maç rating {last.rating:.2f} vs baseline {prior_mean:.2f} "
            f"(z={z:+.2f}, threshold -{k:.1f}σ)"
        ),
        recommended_action=(
            "Antrenmanda izole değerlendirme; fitness/medical check; "
            "1 maç istirahat değerlendir"
        ),
        confidence=round(min(1.0, abs(z) / (k * 2.0)), 2),
    )


def _detect_extended_decline(
    points: list[PerformancePoint], window: int, k_sd: float,
) -> AnomalyEvent | None:
    """Baseline = son `window` maç hariç önceki tüm maçlar."""
    if len(points) < window + 2:
        return None
    prior = points[:-window]
    prior_ratings = [p.rating for p in prior]
    prior_mean = _mean(prior_ratings)
    prior_sd = _sd(prior_ratings, prior_mean)
    if prior_sd <= 0:
        return None
    recent = points[-window:]
    threshold = prior_mean - k_sd * prior_sd
    if not all(p.rating < threshold for p in recent):
        return None
    avg_recent = _mean([p.rating for p in recent])
    delta = prior_mean - avg_recent
    severity = "high" if delta >= 2 * prior_sd else "medium"
    return AnomalyEvent(
        type="extended_decline",
        match_id_seen=recent[-1].match_id,
        severity=severity,
        z_or_factor=round(delta / prior_sd, 2),
        rationale=(
            f"Son {window} maçın hepsi baseline-{k_sd}σ altında "
            f"(ort {avg_recent:.2f} vs {prior_mean:.2f})"
        ),
        recommended_action=(
            "Genel form sorunu — rotasyon + role-fit değerlendirme; "
            "scout görüşü; mental coaching"
        ),
        confidence=0.85,
    )


def _detect_minutes_drop(
    points: list[PerformancePoint], baseline_minutes: float,
) -> AnomalyEvent | None:
    if baseline_minutes <= 0:
        return None
    last = points[-1]
    if last.minute_played >= baseline_minutes * MINUTES_DROP_RATIO:
        return None
    ratio = last.minute_played / baseline_minutes if baseline_minutes else 0
    return AnomalyEvent(
        type="minutes_drop",
        match_id_seen=last.match_id,
        severity="medium" if ratio < 0.25 else "low",
        z_or_factor=round(ratio, 2),
        rationale=(
            f"Son maç {last.minute_played:.0f} dk vs baseline "
            f"{baseline_minutes:.0f} dk ortalama"
        ),
        recommended_action=(
            "Sakatlık/fitness/cezayı doğrula; rotasyon kararını gözden geçir"
        ),
        confidence=round(1.0 - ratio, 2),
    )


def _detect_consistency_collapse(
    points: list[PerformancePoint], recent_n: int = 5,
) -> AnomalyEvent | None:
    if len(points) < recent_n + 5:
        return None
    recent = [p.rating for p in points[-recent_n:]]
    prior = [p.rating for p in points[:-recent_n]]
    if len(prior) < 2 or len(recent) < 2:
        return None
    pm, rm = _mean(prior), _mean(recent)
    psd, rsd = _sd(prior, pm), _sd(recent, rm)
    pcv = psd / abs(pm) if pm != 0 else 0.0
    rcv = rsd / abs(rm) if rm != 0 else 0.0
    if pcv <= 0 or rcv < pcv * CONSISTENCY_COLLAPSE_FACTOR:
        return None
    factor = rcv / pcv
    severity = "high" if factor >= 3.0 else "medium"
    return AnomalyEvent(
        type="consistency_collapse",
        match_id_seen=points[-1].match_id,
        severity=severity,
        z_or_factor=round(factor, 2),
        rationale=(
            f"Son {recent_n} maçın CV {rcv:.2f} vs prior {pcv:.2f} "
            f"(×{factor:.1f}) — volatilite patladı"
        ),
        recommended_action=(
            "Mental coaching / video review; pozisyon stabilitesi sağla; "
            "günlük yorgunluk monitör et"
        ),
        confidence=round(min(1.0, (factor - 1.5) / 2.0), 2),
    )


def _detect_fatigue_buildup(
    points: list[PerformancePoint],
) -> AnomalyEvent | None:
    fatigue_values = [
        p.fatigue_proxy for p in points if p.fatigue_proxy is not None
    ]
    if len(fatigue_values) < 5:
        return None
    overall = _mean(fatigue_values)
    recent = _mean(fatigue_values[-3:])
    if recent - overall < FATIGUE_BUILDUP_DELTA:
        return None
    delta = recent - overall
    severity = "high" if delta >= 0.30 else "medium"
    return AnomalyEvent(
        type="fatigue_buildup",
        match_id_seen=points[-1].match_id,
        severity=severity,
        z_or_factor=round(delta, 2),
        rationale=(
            f"Son 3 maç fatigue {recent:.2f} vs ortalama {overall:.2f} "
            f"(+{delta:.2f})"
        ),
        recommended_action=(
            "Yük azalt + recovery protokolü; bir maç istirahat planı yap"
        ),
        confidence=round(min(1.0, delta / 0.40), 2),
    )


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def compute_performance_anomaly(
    points: Iterable[PerformancePoint],
    *,
    k_sd: float = DEFAULT_K_SD,
    decline_window: int = DEFAULT_DECLINE_WINDOW,
) -> EngineResult[AnomalyReport]:
    plist = list(points)
    notes: list[str] = []

    if len(plist) < MIN_BASELINE_SAMPLES + 1:
        return _empty(
            len(plist),
            f"En az {MIN_BASELINE_SAMPLES + 1} maç gerek "
            f"(baseline + 1 örnek)",
        )

    # Baseline = tüm seri (son maç dahil — z-score için OK)
    ratings = [p.rating for p in plist]
    baseline_mean = _mean(ratings)
    baseline_sd = _sd(ratings, baseline_mean)
    minutes = [p.minute_played for p in plist[:-1]]
    baseline_minutes = _mean(minutes) if minutes else 0.0

    events: list[AnomalyEvent] = []
    for detector in (
        lambda: _detect_sudden_drop(plist, k_sd),
        lambda: _detect_extended_decline(
            plist, decline_window, DEFAULT_DECLINE_SD,
        ),
        lambda: _detect_minutes_drop(plist, baseline_minutes),
        lambda: _detect_consistency_collapse(plist),
        lambda: _detect_fatigue_buildup(plist),
    ):
        ev = detector()
        if ev:
            events.append(ev)

    events.sort(key=lambda e: (-SEVERITY_RANK[e.severity], -e.confidence))

    if events:
        worst = events[0]
        overall_risk = worst.severity
        summary = (
            f"{len(events)} anomali; en kritik: {worst.type} "
            f"({worst.severity.upper()}, conf {worst.confidence:.2f})"
        )
    else:
        overall_risk = "low"
        summary = "Anomali tespit edilmedi — performans baseline'da"

    report = AnomalyReport(
        sample_count=len(plist),
        baseline_mean=round(baseline_mean, 3),
        baseline_sd=round(baseline_sd, 3),
        events=tuple(events),
        summary=summary,
        overall_risk=overall_risk,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="performance_anomaly",
        value={
            "sample_count": len(plist),
            "baseline_mean": round(baseline_mean, 3),
            "baseline_sd": round(baseline_sd, 3),
            "event_count": len(events),
            "event_types": [e.type for e in events],
            "overall_risk": overall_risk,
        },
        inputs={
            "k_sd": k_sd,
            "decline_window": decline_window,
            "minutes_drop_ratio": MINUTES_DROP_RATIO,
            "consistency_collapse_factor": CONSISTENCY_COLLAPSE_FACTOR,
        },
        formula=(
            "5 dedektör: sudden_drop (z ≤ -k·sd), extended_decline (window "
            "ardışık < baseline-1σ), minutes_drop (<%40 baseline dk), "
            "consistency_collapse (CV_recent ≥ 2× CV_prior), fatigue_buildup "
            "(recent_3 - overall ≥ +0.20)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[AnomalyReport]:
    report = AnomalyReport(
        sample_count=n,
        baseline_mean=0.0, baseline_sd=0.0,
        events=(),
        summary=msg, overall_risk="low",
        notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="performance_anomaly",
        value={"sample_count": n, "overall_risk": "low"},
        inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
