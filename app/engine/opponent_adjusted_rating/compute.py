"""Opponent-Strength Adjusted Rating — rakibe göre normalize rating.

Bir oyuncunun maç rating'lerini rakibin kompozit rating'ine göre düzeltir:
güçlü rakibe karşı 7.5 → düşük rakibe karşı 7.5'tan daha değerli.

Formül:
    adjusted = raw + β · (opp_rating - league_avg)
  β default 0.30 (her +1 opp rating → adjusted +0.30)
  league_avg default 7.00 (verilmezse), ya da gelen serinin ortalaması

Çıktı:
  - raw_mean, adjusted_mean, delta (adjusted - raw)
  - per-match AdjustedSample: raw, adjusted, opp_rating, delta_match
  - 3 difficulty bucket: easy (opp ≤6.5), average (6.5-7.5), tough (≥7.5)
    her bucket için n, raw_mean, adjusted_mean
  - over/under-performance: en yüksek pozitif/negatif Δ maç

Pure compute.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.opponent_adjusted_rating"
ENGINE_VERSION = "1"

DEFAULT_BETA = 0.30
DEFAULT_LEAGUE_AVG = 7.00
EASY_THRESHOLD = 6.5
TOUGH_THRESHOLD = 7.5


@dataclass(frozen=True)
class PerformanceVsOpponent:
    match_id: int
    rating: float                         # 0..10 raw rating
    opp_rating: float                     # 0..10 rakibin kompozit rating'i


@dataclass(frozen=True)
class AdjustedSample:
    match_id: int
    raw: float
    opp_rating: float
    adjusted: float
    delta: float                          # adjusted - raw
    bucket: str                           # easy | average | tough


@dataclass(frozen=True)
class DifficultyBucket:
    name: str                             # easy | average | tough
    n: int
    raw_mean: float
    adjusted_mean: float


@dataclass(frozen=True)
class AdjustedRatingReport:
    sample_count: int
    raw_mean: float
    adjusted_mean: float
    delta_mean: float                     # adjusted_mean - raw_mean
    league_avg_used: float
    beta: float
    samples: tuple[AdjustedSample, ...]
    buckets: tuple[DifficultyBucket, ...]
    top_overperformance_match: int | None
    top_underperformance_match: int | None
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _bucket_for(opp_rating: float) -> str:
    if opp_rating <= EASY_THRESHOLD:
        return "easy"
    if opp_rating >= TOUGH_THRESHOLD:
        return "tough"
    return "average"


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute_opponent_adjusted_rating(
    samples: Iterable[PerformanceVsOpponent],
    *,
    beta: float = DEFAULT_BETA,
    league_avg: float | None = None,
) -> EngineResult[AdjustedRatingReport]:
    slist = list(samples)
    notes: list[str] = []

    if not slist:
        return _empty(0, "Sample yok")

    if league_avg is None:
        # Serinin opponent ortalaması — verilmezse gerçekçi default
        league_avg = _mean([s.opp_rating for s in slist])
        if league_avg <= 0:
            league_avg = DEFAULT_LEAGUE_AVG

    # Adjust her sample
    adjusted_samples: list[AdjustedSample] = []
    for s in slist:
        adj = s.rating + beta * (s.opp_rating - league_avg)
        adj = max(0.0, min(10.0, adj))     # clamp 0..10
        adjusted_samples.append(AdjustedSample(
            match_id=s.match_id,
            raw=round(s.rating, 3),
            opp_rating=round(s.opp_rating, 3),
            adjusted=round(adj, 3),
            delta=round(adj - s.rating, 3),
            bucket=_bucket_for(s.opp_rating),
        ))

    raw_mean = _mean([s.raw for s in adjusted_samples])
    adjusted_mean = _mean([s.adjusted for s in adjusted_samples])

    # Buckets
    buckets: list[DifficultyBucket] = []
    for bname in ("easy", "average", "tough"):
        group = [a for a in adjusted_samples if a.bucket == bname]
        if not group:
            continue
        buckets.append(DifficultyBucket(
            name=bname,
            n=len(group),
            raw_mean=round(_mean([a.raw for a in group]), 3),
            adjusted_mean=round(_mean([a.adjusted for a in group]), 3),
        ))

    # Over / under performance
    if adjusted_samples:
        sorted_by_delta = sorted(adjusted_samples, key=lambda a: -a.delta)
        top_over = sorted_by_delta[0]
        top_under = sorted_by_delta[-1]
        top_over_match = top_over.match_id if top_over.delta > 0 else None
        top_under_match = top_under.match_id if top_under.delta < 0 else None
    else:
        top_over_match = None
        top_under_match = None

    if not slist:
        notes.append("Sample yok")
    if all(s.opp_rating == slist[0].opp_rating for s in slist):
        notes.append(
            "Tüm rakipler eşit güçte — adjustment etkisi sıfır",
        )

    summary = (
        f"Raw mean {raw_mean:.2f} → adjusted mean {adjusted_mean:.2f} "
        f"(Δ {adjusted_mean - raw_mean:+.2f}); league_avg {league_avg:.2f}"
    )

    report = AdjustedRatingReport(
        sample_count=len(slist),
        raw_mean=round(raw_mean, 3),
        adjusted_mean=round(adjusted_mean, 3),
        delta_mean=round(adjusted_mean - raw_mean, 3),
        league_avg_used=round(league_avg, 3),
        beta=beta,
        samples=tuple(adjusted_samples),
        buckets=tuple(buckets),
        top_overperformance_match=top_over_match,
        top_underperformance_match=top_under_match,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="opponent_adjusted_rating",
        value={
            "sample_count": len(slist),
            "raw_mean": round(raw_mean, 3),
            "adjusted_mean": round(adjusted_mean, 3),
            "delta_mean": round(adjusted_mean - raw_mean, 3),
            "league_avg": round(league_avg, 3),
            "beta": beta,
            "bucket_counts": {b.name: b.n for b in buckets},
        },
        inputs={
            "beta": beta,
            "league_avg": round(league_avg, 3),
            "thresholds": {"easy": EASY_THRESHOLD, "tough": TOUGH_THRESHOLD},
        },
        formula=(
            "adjusted = raw + β · (opp_rating - league_avg); "
            "bucket = easy(≤6.5) | average | tough(≥7.5)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[AdjustedRatingReport]:
    report = AdjustedRatingReport(
        sample_count=n,
        raw_mean=0.0, adjusted_mean=0.0, delta_mean=0.0,
        league_avg_used=DEFAULT_LEAGUE_AVG, beta=DEFAULT_BETA,
        samples=(), buckets=(),
        top_overperformance_match=None,
        top_underperformance_match=None,
        summary=msg, notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="opponent_adjusted_rating",
        value={"sample_count": n}, inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
