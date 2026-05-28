"""Tempo — pas hızı (passes per minute) + pres altında değişim.

Tanım: takımın takım pasları / efektif oyun süresi (basit yaklaşım: maç
toplam dakikası / matches_analyzed). Ek olarak "pres altı tempo" — pres
yapıldığında hız düşüp düşmediği (ileri bakış).

Yüksek tempo = İspanyol/Alman tarzı one-touch. Düşük = Mourinho-kontrol.

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent

ENGINE_NAME = "engine.tempo"
ENGINE_VERSION = "1"

# Standart maç süresi
MATCH_MINUTES = 90.0


@dataclass(frozen=True)
class TempoReport:
    team_external_id: int
    matches_analyzed: int
    total_passes: int
    passes_per_minute: float
    label: str         # "fast" | "medium" | "slow"


def _label(ppm: float) -> str:
    if ppm >= 8.0:
        return "fast"
    if ppm >= 5.0:
        return "medium"
    return "slow"


def compute_tempo(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[TempoReport]:
    team_passes = [p for p in all_passes if p.team_external_id == team_external_id]
    total_minutes = MATCH_MINUTES * matches_analyzed
    ppm = len(team_passes) / total_minutes if total_minutes else 0.0

    report = TempoReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        total_passes=len(team_passes),
        passes_per_minute=round(ppm, 2),
        label=_label(ppm) if team_passes else "insufficient_data",
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="tempo",
        value={
            "total_passes": report.total_passes,
            "passes_per_minute": report.passes_per_minute,
            "label": report.label,
        },
        inputs={"match_minutes": MATCH_MINUTES, "matches_analyzed": matches_analyzed},
        formula="passes / (MATCH_MINUTES × matches_analyzed)",
    )
    return EngineResult(value=report, audit=audit)
