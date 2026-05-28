"""Team Compactness — savunma-orta-hücum hattı arası mesafe.

Tracking olmadan tam ölçülemez; biz event proxy kullanıyoruz:
- Defansif aksiyonların **x-stdev**'i: savunma hattının dağınıklığı.
- Pasların **x-stdev**'i: takımın dikey yayılımı.

Düşük stdev = kompakt blok (Atletico Madrid Simeone). Yüksek stdev =
geniş açık takım (Klopp transition).

Saf hesap. PassEvent + DefensiveAction → CompactnessReport.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.compactness"
ENGINE_VERSION = "1"

# Eşikler: x-stdev (100×100 saha)
COMPACT_STDEV_MAX = 18.0       # ≤18 → kompakt
LOOSE_STDEV_MIN = 28.0         # ≥28 → açık


@dataclass(frozen=True)
class CompactnessReport:
    team_external_id: int
    matches_analyzed: int
    def_actions_counted: int
    passes_counted: int
    def_x_stdev: float            # savunma yayılımı
    pass_x_stdev: float           # genel takım yayılımı
    overall_stdev: float          # ikisinin ortalaması
    label: str                    # "compact" | "balanced" | "stretched"


def _stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def _label(stdev: float) -> str:
    if stdev <= COMPACT_STDEV_MAX:
        return "compact"
    if stdev >= LOOSE_STDEV_MIN:
        return "stretched"
    return "balanced"


def compute_compactness(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[CompactnessReport]:
    team_passes_x = [
        p.start_x for p in all_passes
        if p.team_external_id == team_external_id
    ]
    team_def_x = [
        d.x for d in all_def_actions
        if d.team_external_id == team_external_id
    ]

    def_stdev = _stdev(team_def_x)
    pass_stdev = _stdev(team_passes_x)
    overall = (def_stdev + pass_stdev) / 2 if (team_def_x or team_passes_x) else 0.0

    label = _label(overall) if (team_def_x or team_passes_x) else "insufficient_data"

    report = CompactnessReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        def_actions_counted=len(team_def_x),
        passes_counted=len(team_passes_x),
        def_x_stdev=round(def_stdev, 2),
        pass_x_stdev=round(pass_stdev, 2),
        overall_stdev=round(overall, 2),
        label=label,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="team_compactness",
        value={
            "def_x_stdev": report.def_x_stdev,
            "pass_x_stdev": report.pass_x_stdev,
            "overall_stdev": report.overall_stdev,
            "label": report.label,
        },
        inputs={
            "compact_stdev_max": COMPACT_STDEV_MAX,
            "loose_stdev_min": LOOSE_STDEV_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="mean(stdev(def_action.x), stdev(pass.start_x))",
    )
    return EngineResult(value=report, audit=audit)
