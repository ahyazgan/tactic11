"""Clutch Performance — kritik anlarda performans katsayısı.

Bir oyuncunun maç rating'lerini "önemli/baskı" durumuna göre filtreleyip
ortalama karşılaştırması yapar. Çıktı: clutch_factor (= clutch_mean /
overall_mean) ve "clutch / neutral / chokes" etiketi.

Önem boyutları (her maç başına dict flag'ları):
  - big_match    : derbi, final, üst sıra rakip vs.
  - close_game   : skor farkı ≤ 1 (yakın maç)
  - late_minute  : son 15 dk oynanan dakika varsa (asistan/kapatma rolü)
  - knockout     : direkt eleme (Champions L. R16+, kupa final vs.)
  - opp_strong   : rakip kompozit rating ≥ 7.5

ClutchSample = (match_id, rating, importance_flags dict).
SituationBreakdown her boyut için ayrı: n, mean_in, mean_out, factor.

Pure compute.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.clutch_performance"
ENGINE_VERSION = "1"

SUPPORTED_DIMENSIONS = (
    "big_match",
    "close_game",
    "late_minute",
    "knockout",
    "opp_strong",
)

CLUTCH_FACTOR_THRESHOLD = 1.10
CHOKES_FACTOR_THRESHOLD = 0.95
MIN_CLUTCH_SAMPLES = 3


@dataclass(frozen=True)
class ClutchSample:
    match_id: int
    rating: float
    flags: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class SituationBreakdown:
    dimension: str                  # big_match, close_game, ...
    n_in: int                       # bu önem durumundaki maç sayısı
    n_out: int                      # diğer maç sayısı
    mean_in: float
    mean_out: float
    factor: float                   # mean_in / mean_out (0 if mean_out == 0)
    delta: float                    # mean_in - mean_out


@dataclass(frozen=True)
class ClutchReport:
    sample_count: int
    overall_mean: float
    clutch_mean: float              # en az 1 önem flag açık olanların ort.
    clutch_factor: float            # clutch_mean / overall_mean
    label: str                      # clutch | neutral | chokes | insufficient
    per_situation: tuple[SituationBreakdown, ...]
    strongest_clutch: str | None    # en güçlü pozitif boyut
    weakest_clutch: str | None      # en kötü boyut
    summary: str                    # TR 1-cümle
    notes: tuple[str, ...] = field(default_factory=tuple)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _label_from_factor(factor: float, clutch_n: int) -> str:
    if clutch_n < MIN_CLUTCH_SAMPLES:
        return "insufficient"
    if factor >= CLUTCH_FACTOR_THRESHOLD:
        return "clutch"
    if factor < CHOKES_FACTOR_THRESHOLD:
        return "chokes"
    return "neutral"


def compute_clutch_performance(
    samples: Iterable[ClutchSample],
) -> EngineResult[ClutchReport]:
    slist = list(samples)
    notes: list[str] = []

    if len(slist) < 2:
        return _empty(len(slist), "En az 2 maç gerek")

    overall_mean = _mean([s.rating for s in slist])

    # Per-situation breakdowns
    per_situation: list[SituationBreakdown] = []
    for dim in SUPPORTED_DIMENSIONS:
        in_samples = [s.rating for s in slist if s.flags.get(dim, False)]
        out_samples = [s.rating for s in slist if not s.flags.get(dim, False)]
        if not in_samples:
            continue
        mean_in = _mean(in_samples)
        mean_out = _mean(out_samples) if out_samples else 0.0
        factor = mean_in / mean_out if mean_out > 0 else 0.0
        per_situation.append(SituationBreakdown(
            dimension=dim,
            n_in=len(in_samples), n_out=len(out_samples),
            mean_in=round(mean_in, 3),
            mean_out=round(mean_out, 3),
            factor=round(factor, 3),
            delta=round(mean_in - mean_out, 3),
        ))

    # Aggregate clutch: en az 1 flag açık olanlar
    clutch_samples = [
        s.rating for s in slist
        if any(s.flags.get(d, False) for d in SUPPORTED_DIMENSIONS)
    ]
    clutch_mean = _mean(clutch_samples) if clutch_samples else 0.0
    clutch_factor = clutch_mean / overall_mean if overall_mean > 0 else 0.0
    label = _label_from_factor(clutch_factor, len(clutch_samples))

    if not clutch_samples:
        notes.append("Hiçbir maç için önem flag'i set edilmedi — clutch karşılaştırması yapılamadı")
    elif len(clutch_samples) < MIN_CLUTCH_SAMPLES:
        notes.append(f"Yalnız {len(clutch_samples)} kritik maç — etiket güvenilir değil")

    # Strongest / weakest dimension by delta
    strongest: str | None = None
    weakest: str | None = None
    if per_situation:
        sorted_by_delta = sorted(per_situation, key=lambda b: -b.delta)
        strongest = sorted_by_delta[0].dimension if sorted_by_delta[0].delta > 0 else None
        weakest_candidate = sorted_by_delta[-1]
        weakest = weakest_candidate.dimension if weakest_candidate.delta < 0 else None

    if label == "insufficient":
        summary = (
            f"{len(slist)} maç, {len(clutch_samples)} kritik maç — "
            f"clutch etiketi için yetersiz"
        )
    else:
        summary = (
            f"Clutch factor {clutch_factor:.2f} — {label}; "
            f"genel {overall_mean:.2f}, kritik {clutch_mean:.2f}"
        )

    report = ClutchReport(
        sample_count=len(slist),
        overall_mean=round(overall_mean, 3),
        clutch_mean=round(clutch_mean, 3),
        clutch_factor=round(clutch_factor, 3),
        label=label,
        per_situation=tuple(per_situation),
        strongest_clutch=strongest,
        weakest_clutch=weakest,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="clutch_performance",
        value={
            "sample_count": len(slist),
            "clutch_factor": round(clutch_factor, 3),
            "label": label,
            "clutch_sample_count": len(clutch_samples),
            "dimensions_with_data": [b.dimension for b in per_situation],
            "strongest_clutch": strongest,
            "weakest_clutch": weakest,
        },
        inputs={
            "supported_dimensions": list(SUPPORTED_DIMENSIONS),
            "thresholds": {
                "clutch": CLUTCH_FACTOR_THRESHOLD,
                "chokes": CHOKES_FACTOR_THRESHOLD,
                "min_clutch_samples": MIN_CLUTCH_SAMPLES,
            },
        },
        formula=(
            "clutch_factor = mean(rating | any flag) / mean(rating); "
            "per_situation.factor = mean_in / mean_out per dimension; "
            "label = clutch(≥1.10) | neutral | chokes(<0.95)"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[ClutchReport]:
    report = ClutchReport(
        sample_count=n,
        overall_mean=0.0, clutch_mean=0.0,
        clutch_factor=0.0, label="insufficient",
        per_situation=(),
        strongest_clutch=None, weakest_clutch=None,
        summary=msg, notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="clutch_performance",
        value={"sample_count": n, "label": "insufficient"},
        inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
