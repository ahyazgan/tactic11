"""Defensive Line Height — savunma hattının ortalama yüksekliği.

Tanım: takımın defansif aksiyonlarının (tackle, interception, ball_recovery,
clearance, block) ortalama x-koordinatı. Yüksek = ileri savunma hattı
(City, Bayern); düşük = derin blok (klasik İtalyan).

Saf hesap. DefensiveAction listesinden tek sayı + label çıkarır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction

ENGINE_NAME = "engine.defensive_line"
ENGINE_VERSION = "1"

# Saha 100 birim; x referansı: 0 = kendi kalemiz, 100 = rakip kalesi.
HIGH_LINE_X_MIN = 50.0      # avg x ≥ 50 → ileri hat
MID_LINE_X_MIN = 35.0       # 35–50 → orta hat
# < 35 → derin blok

# "Pressure" eventlerini hat yüksekliğinden hariç tutuyoruz çünkü onlar
# saldırgan baskı; savunma çizgisini bozar (oyuncu ileri çıkar)
LINE_HEIGHT_ACTIONS = (
    "tackle", "interception", "ball_recovery", "clearance", "block",
)


@dataclass(frozen=True)
class DefensiveLineReport:
    team_external_id: int
    matches_analyzed: int
    actions_counted: int
    avg_x: float
    median_x: float
    p25_x: float                  # alt-çeyrek (derin oyuncular)
    p75_x: float                  # üst-çeyrek (yüksek oyuncular)
    line_label: str               # "high" | "mid" | "low"


def _label(avg_x: float) -> str:
    if avg_x >= HIGH_LINE_X_MIN:
        return "high"
    if avg_x >= MID_LINE_X_MIN:
        return "mid"
    return "low"


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def compute_defensive_line(
    team_external_id: int,
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[DefensiveLineReport]:
    xs = sorted(
        d.x for d in all_def_actions
        if d.team_external_id == team_external_id
        and d.action_type in LINE_HEIGHT_ACTIONS
    )

    if not xs:
        report = DefensiveLineReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            actions_counted=0,
            avg_x=0.0, median_x=0.0, p25_x=0.0, p75_x=0.0,
            line_label="insufficient_data",
        )
    else:
        avg_x = sum(xs) / len(xs)
        report = DefensiveLineReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            actions_counted=len(xs),
            avg_x=round(avg_x, 2),
            median_x=round(_percentile(xs, 0.5), 2),
            p25_x=round(_percentile(xs, 0.25), 2),
            p75_x=round(_percentile(xs, 0.75), 2),
            line_label=_label(avg_x),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="defensive_line_height",
        value={
            "actions_counted": report.actions_counted,
            "avg_x": report.avg_x,
            "median_x": report.median_x,
            "line_label": report.line_label,
        },
        inputs={
            "high_line_x_min": HIGH_LINE_X_MIN,
            "mid_line_x_min": MID_LINE_X_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="mean(def_action.x) for tackle/interception/recovery/clearance/block",
    )
    return EngineResult(value=report, audit=audit)
