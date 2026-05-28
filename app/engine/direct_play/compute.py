"""Direct Play Index — Sumpter "directness" metriği.

Tanım: takımın paslarının "ileri-x mesafesi / toplam-mesafesi" ortalaması.
Saf yatay pas = 0.0 directness. Kale yönünde dik pas = ~1.0.

Yüksek = top'u doğrudan ileri taşıyan takım (Burnley, Sean Dyche).
Düşük = side-to-side metodik (Pep City).

Saf hesap.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.direct_play"
ENGINE_VERSION = "1"

# Çok kısa paslar (1 birim altı) gürültü — çıkar
MIN_PASS_DISTANCE = 1.0


@dataclass(frozen=True)
class DirectPlayReport:
    team_external_id: int
    matches_analyzed: int
    passes_analyzed: int
    avg_directness: float        # mean(forward_dx / total_dist), 0-1
    forward_pass_share: float    # end_x > start_x oranı
    style_label: str             # "direct" | "balanced" | "possession"


def _label(avg: float) -> str:
    if avg >= 0.55:
        return "direct"
    if avg >= 0.35:
        return "balanced"
    return "possession"


def compute_direct_play(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[DirectPlayReport]:
    team_passes = [
        p for p in all_passes
        if p.team_external_id == team_external_id
    ]
    forward = 0
    direct_values: list[float] = []
    for p in team_passes:
        dx = p.end_x - p.start_x
        dy = p.end_y - p.start_y
        dist = math.hypot(dx, dy)
        if dist < MIN_PASS_DISTANCE:
            continue
        # negative forward (= geri pas) clamp 0
        directness = max(0.0, dx) / dist
        direct_values.append(directness)
        if dx > 0:
            forward += 1

    if not direct_values:
        report = DirectPlayReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            passes_analyzed=0,
            avg_directness=0.0,
            forward_pass_share=0.0,
            style_label="insufficient_data",
        )
    else:
        avg = sum(direct_values) / len(direct_values)
        report = DirectPlayReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            passes_analyzed=len(direct_values),
            avg_directness=round(avg, 3),
            forward_pass_share=round(forward / len(direct_values), 3),
            style_label=_label(avg),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="direct_play_index",
        value={
            "avg_directness": report.avg_directness,
            "forward_pass_share": report.forward_pass_share,
            "style_label": report.style_label,
            "passes_analyzed": report.passes_analyzed,
        },
        inputs={"min_pass_distance": MIN_PASS_DISTANCE,
                "matches_analyzed": matches_analyzed},
        formula="mean(max(0, dx) / total_dist) over passes (Sumpter directness)",
    )
    return EngineResult(value=report, audit=audit)
