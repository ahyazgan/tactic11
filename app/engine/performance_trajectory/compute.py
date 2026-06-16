"""Performance Trajectory — rating zaman serisi slope analizi.

Bir oyuncunun maç-maç KPI dizisinden:
  - linear regression slope (rating delta per game-index)
  - direction: improving | declining | stable
  - confidence (0..1): residual std vs slope magnitude
  - peak_index, dip_index
  - projection_next_3: önümüzdeki 3 maç tahmini (slope + last_value)
  - smoothed_series (3-game moving avg)
  - regression_to_mean_warning: aşırı yüksek/düşük serinin geri çekilme uyarısı

Pure compute. Match order = chronological (first → last).
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.performance_trajectory"
ENGINE_VERSION = "1"

SLOPE_STABLE_THRESHOLD = 0.05   # |slope| < 0.05 → stable
RTM_DEVIATION_THRESHOLD = 1.5   # |mean - 7| > 1.5 → regression warning


@dataclass(frozen=True)
class TrajectoryPoint:
    match_id: int
    value: float
    game_index: int                 # 0..n-1, kronolojik


@dataclass(frozen=True)
class TrajectoryReport:
    sample_count: int
    slope: float                    # rating per match
    intercept: float                # baseline value
    direction: str                  # improving | declining | stable | insufficient
    confidence: float               # 0..1
    peak_index: int                 # 0..n-1 (en yüksek değer indeksi)
    dip_index: int
    last_value: float
    projection_next_3: tuple[float, float, float]
    smoothed_series: tuple[float, ...]
    rtm_warning: str | None         # regression-to-mean uyarısı, varsa
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Slope, intercept, residual std."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0, 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0, mean_y, 0.0
    slope = num / den
    intercept = mean_y - slope * mean_x
    residuals = [ys[i] - (slope * xs[i] + intercept) for i in range(n)]
    rsd = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2)) if n > 2 else 0.0
    return slope, intercept, rsd


def _direction(slope: float) -> str:
    if abs(slope) < SLOPE_STABLE_THRESHOLD:
        return "stable"
    return "improving" if slope > 0 else "declining"


def _confidence(slope: float, rsd: float) -> float:
    """|slope| / (rsd + epsilon) → 0..1 clamp."""
    if rsd <= 0:
        # zero variance — slope kesin
        return 1.0 if abs(slope) > 0 else 0.5
    ratio = abs(slope) / (rsd + 0.05)
    return round(min(1.0, ratio), 3)


def _smooth(values: list[float], window: int = 3) -> list[float]:
    if not values:
        return []
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - window // 2)
        hi = min(len(values), i + window // 2 + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return [round(v, 3) for v in out]


def _rtm_warning(values: list[float]) -> str | None:
    """Aşırı sapma → ortalamaya dönme beklentisi."""
    n = len(values)
    if n < 5:
        return None
    last_5 = values[-5:]
    last_5_mean = sum(last_5) / len(last_5)
    if last_5_mean > 7 + RTM_DEVIATION_THRESHOLD:
        return (
            f"Son 5 ortalama {last_5_mean:.2f} — anormal yüksek, "
            "regression-to-mean beklenebilir"
        )
    if last_5_mean < 7 - RTM_DEVIATION_THRESHOLD:
        return (
            f"Son 5 ortalama {last_5_mean:.2f} — anormal düşük, "
            "toparlanma beklenebilir"
        )
    return None


def compute_performance_trajectory(
    points: Iterable[TrajectoryPoint],
) -> EngineResult[TrajectoryReport]:
    plist = sorted(list(points), key=lambda p: p.game_index)
    notes: list[str] = []

    if len(plist) < 2:
        return _empty(len(plist), "En az 2 örnek gerek")

    xs = [float(p.game_index) for p in plist]
    ys = [float(p.value) for p in plist]
    slope, intercept, rsd = _linreg(xs, ys)
    direction = _direction(slope)
    conf = _confidence(slope, rsd)

    peak_idx = max(range(len(ys)), key=lambda i: ys[i])
    dip_idx = min(range(len(ys)), key=lambda i: ys[i])

    last_x = xs[-1]
    proj = (
        round(slope * (last_x + 1) + intercept, 3),
        round(slope * (last_x + 2) + intercept, 3),
        round(slope * (last_x + 3) + intercept, 3),
    )
    smoothed = _smooth(ys)
    rtm = _rtm_warning(ys)

    if len(plist) < 5:
        notes.append("Az örnek — slope yorumu sınırlı")
    if rtm:
        notes.append(rtm)

    summary = (
        f"{direction} (slope {slope:+.3f}/maç, conf {conf:.2f}); "
        f"peak dk {peak_idx}, dip dk {dip_idx}; "
        f"projeksiyon: {proj[0]:.2f}/{proj[1]:.2f}/{proj[2]:.2f}"
    )

    report = TrajectoryReport(
        sample_count=len(plist),
        slope=round(slope, 4),
        intercept=round(intercept, 3),
        direction=direction,
        confidence=conf,
        peak_index=peak_idx,
        dip_index=dip_idx,
        last_value=round(ys[-1], 3),
        projection_next_3=proj,
        smoothed_series=tuple(smoothed),
        rtm_warning=rtm,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=0,
        metric="performance_trajectory",
        value={
            "sample_count": len(plist),
            "slope": round(slope, 4),
            "direction": direction,
            "confidence": conf,
            "peak_index": peak_idx,
            "dip_index": dip_idx,
            "rtm_warning": rtm,
        },
        inputs={
            "thresholds": {
                "slope_stable": SLOPE_STABLE_THRESHOLD,
                "rtm_deviation": RTM_DEVIATION_THRESHOLD,
            },
        },
        formula=(
            "OLS linear regression on (game_index, value); "
            "direction = stable(|slope|<0.05) else improving/declining; "
            "confidence = clamp(|slope|/(rsd+0.05), 0..1); "
            "projection = slope*(last_x+k) + intercept for k=1,2,3"
        ),
    )
    return EngineResult(value=report, audit=audit)


def _empty(n: int, msg: str) -> EngineResult[TrajectoryReport]:
    report = TrajectoryReport(
        sample_count=n,
        slope=0.0, intercept=0.0,
        direction="insufficient",
        confidence=0.0,
        peak_index=0, dip_index=0,
        last_value=0.0,
        projection_next_3=(0.0, 0.0, 0.0),
        smoothed_series=(),
        rtm_warning=None,
        summary=msg,
        notes=(msg,),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=0,
        metric="performance_trajectory",
        value={"sample_count": n, "direction": "insufficient"},
        inputs={}, formula="insufficient",
    )
    return EngineResult(value=report, audit=audit)
