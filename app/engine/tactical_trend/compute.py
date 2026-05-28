"""Tactical Trend — bir metriğin maç-bazlı zaman serisi + slope analizi.

Tek-maç engine'leri sezon görünümüne çevirir:
- PPDA trend: son 10 maçta pres yoğunluğu artıyor mu?
- Field tilt trend: hücum yarısı hakimiyeti zaman içinde nasıl değişiyor?
- Coaching identity drift: koç vektörü ne kadar değişti?

Saf hesap. Caller match-bazlı sayı listesi gönderir; biz slope (linear
regression) + direction label + volatility (stdev) çıkarırız.

Birim-bağımsız: caller hangi metrikse onu gönderir (PPDA, tilt %, xG diff,
vs.). Çıktı sadece trend göstergesidir.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.tactical_trend"
ENGINE_VERSION = "1"

# Yön etiketleri (slope normalize % of mean)
DIRECTION_THRESHOLD = 0.10  # |slope/mean| < 0.10 → stable


@dataclass(frozen=True)
class TacticalTrendReport:
    metric_name: str
    matches_analyzed: int
    series: tuple[float, ...]               # kronolojik değerler
    mean: float
    stdev: float                            # volatility
    slope: float                            # linear regression eğimi
    slope_pct_of_mean: float                # |slope| / |mean|
    direction: str                          # "improving" | "stable" | "worsening"
    # "improving" ne anlama gelir — caller'a bağlı (higher_is_better):
    higher_is_better: bool
    # En büyük tek-maç değişimi (ardışık fark)
    biggest_match_to_match_shift: float
    biggest_shift_match_idx: int            # 0-indexed


def _linear_regression_slope(ys: list[float]) -> float:
    """Sıralı zaman serisi için basit slope (x = 0, 1, ..., n-1)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = (n - 1) / 2
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def _direction(slope: float, mean: float, *, higher_is_better: bool) -> str:
    if mean == 0:
        return "stable"
    pct = abs(slope) / abs(mean)
    if pct < DIRECTION_THRESHOLD:
        return "stable"
    # higher_is_better=True → slope positive iyileşme
    # higher_is_better=False → slope negative iyileşme (PPDA: düşük=iyi)
    going_up = slope > 0
    if (going_up and higher_is_better) or (not going_up and not higher_is_better):
        return "improving"
    return "worsening"


def _biggest_shift(series: list[float]) -> tuple[float, int]:
    """En büyük ardışık |delta| + hangi indekste."""
    if len(series) < 2:
        return 0.0, 0
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    abs_deltas = [abs(d) for d in deltas]
    idx = abs_deltas.index(max(abs_deltas))
    return round(deltas[idx], 4), idx + 1  # +1 çünkü delta i-th match'i etkiler


def compute_tactical_trend(
    metric_name: str,
    series: Iterable[float],
    *,
    higher_is_better: bool = False,
    subject_type: str = "team",
    subject_id: int = 0,
) -> EngineResult[TacticalTrendReport]:
    """Bir metriğin zaman serisinden trend raporu.

    `series` kronolojik (en eski → en yeni). higher_is_better metriğin
    semantiğini taşır (PPDA için False, xG için True).
    """
    series_list = [float(v) for v in series if v is not None]
    n = len(series_list)
    if n == 0:
        report = TacticalTrendReport(
            metric_name=metric_name, matches_analyzed=0,
            series=(), mean=0.0, stdev=0.0,
            slope=0.0, slope_pct_of_mean=0.0,
            direction="insufficient_data",
            higher_is_better=higher_is_better,
            biggest_match_to_match_shift=0.0,
            biggest_shift_match_idx=0,
        )
    else:
        mean = sum(series_list) / n
        sd = _stdev(series_list)
        sl = _linear_regression_slope(series_list)
        pct = abs(sl) / abs(mean) if mean != 0 else 0.0
        biggest, idx = _biggest_shift(series_list)
        report = TacticalTrendReport(
            metric_name=metric_name,
            matches_analyzed=n,
            series=tuple(round(v, 4) for v in series_list),
            mean=round(mean, 4),
            stdev=round(sd, 4),
            slope=round(sl, 4),
            slope_pct_of_mean=round(pct, 4),
            direction=_direction(sl, mean, higher_is_better=higher_is_better),
            higher_is_better=higher_is_better,
            biggest_match_to_match_shift=biggest,
            biggest_shift_match_idx=idx,
        )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type=subject_type, subject_id=subject_id,
        metric=f"trend_{metric_name}",
        value={
            "matches_analyzed": report.matches_analyzed,
            "mean": report.mean, "stdev": report.stdev,
            "slope": report.slope,
            "direction": report.direction,
            "biggest_shift": report.biggest_match_to_match_shift,
            "biggest_shift_match_idx": report.biggest_shift_match_idx,
        },
        inputs={
            "higher_is_better": higher_is_better,
            "direction_threshold": DIRECTION_THRESHOLD,
        },
        formula="linear regression slope; direction by |slope/mean| vs threshold",
    )
    return EngineResult(value=report, audit=audit)
