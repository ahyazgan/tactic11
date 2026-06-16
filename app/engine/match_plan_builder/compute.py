"""Match Plan Builder — H + I + K kompozisyonu ile 1-sayfa maç planı.

Tek motor, üç motor çağırır:
  - engine.formation_matchup → 8-vektör + 3 advice
  - engine.set_piece_library → top 2 routine (ofansif)
  - engine.threat_pathway   → bizim exploit lane'i (event verildiyse)

Çıktı (MatchPlan): kompakt JSON yapı, AI prompt veya TD brifingi için doğrudan
kullanılabilir. Pure compute, başka motorların pure çıktısını compose eder.

Audit: alt motorların audit özeti bu motorun audit.inputs'ında saklanır
(traceability).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.engine.formation_matchup import compute_formation_matchup
from app.engine.set_piece_library import (
    SetPieceContext,
    compute_set_piece_recommendation,
)
from app.engine.threat_pathway import PathwayEvent, compute_threat_pathway

ENGINE_NAME = "engine.match_plan_builder"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class MatchPlanContext:
    """Plan üretmek için minimum girdi seti."""
    our_formation: str
    opp_formation: str
    opponent_style: str | None = None              # set-piece bonus için
    set_piece_type: str = "corner"
    set_piece_side: str | None = "long"
    our_attributes: dict[str, float] = field(default_factory=dict)
    recent_threat_events: Iterable[PathwayEvent] | None = None


@dataclass(frozen=True)
class MatchPlan:
    our_formation: str
    opp_formation: str
    matchup_vector: dict[str, float]               # 8 vektör
    matchup_advice: tuple[str, ...]
    set_piece_top: tuple[dict[str, object], ...]   # name, score, label
    threat_top_lane: str | None
    threat_advice: str | None
    headline: str                                  # 1-cümle özet
    plan_lines: tuple[str, ...]                    # 3-6 satır kompakt brifing
    notes: tuple[str, ...] = field(default_factory=tuple)


def compute_match_plan(ctx: MatchPlanContext) -> EngineResult[MatchPlan]:
    notes: list[str] = []

    # 1) Formasyon eşleşmesi
    fmu = compute_formation_matchup(
        our_formation=ctx.our_formation, opp_formation=ctx.opp_formation,
    )
    fmu_report = fmu.value
    matchup_vector = dict(fmu_report.expectation.values)
    matchup_advice = tuple(fmu_report.advice)
    if fmu_report.notes:
        notes.extend(fmu_report.notes)

    # 2) Set-piece önerisi (ofansif)
    sp_ctx = SetPieceContext(
        type=ctx.set_piece_type,
        side=ctx.set_piece_side,
        our_attributes=ctx.our_attributes,
        opponent_style=ctx.opponent_style,
    )
    sp = compute_set_piece_recommendation(sp_ctx, top_n=2)
    sp_report = sp.value
    sp_top = tuple(
        {"name": p.name, "label": p.label, "score": round(p.score, 1)}
        for p in sp_report.top_recommendations
    )
    if sp_report.notes:
        notes.extend(sp_report.notes)

    # 3) Threat pathway (event verildiyse)
    threat_lane: str | None = None
    threat_advice: str | None = None
    if ctx.recent_threat_events is not None:
        tp = compute_threat_pathway(ctx.recent_threat_events)
        tp_report = tp.value
        threat_lane = tp_report.top_lane
        threat_advice = tp_report.our_exploit_advice if threat_lane else None
        if not tp_report.total_events:
            notes.append("Threat event yok — lane planı boş")

    # 4) Headline + plan satırları
    headline = (
        f"{ctx.our_formation} vs {ctx.opp_formation} — "
        f"PPDA üstünlüğü {matchup_vector.get('our_ppda_advantage', 0.5):+.2f}, "
        f"orta saha kontrol {matchup_vector.get('midfield_control', 0.5):.2f}"
    )

    plan_lines: list[str] = []
    if matchup_advice:
        plan_lines.append("Formasyon: " + matchup_advice[0])
        if len(matchup_advice) > 1:
            plan_lines.append("Risk: " + matchup_advice[1])
    if sp_top:
        plan_lines.append(
            f"Set-piece: {sp_top[0]['label']} ({ctx.set_piece_type})",
        )
    if threat_lane:
        plan_lines.append(f"Lane planı: {threat_lane} → {threat_advice}")
    if not plan_lines:
        plan_lines.append("Yetersiz girdi — temel formasyon planı uygula")

    plan = MatchPlan(
        our_formation=ctx.our_formation,
        opp_formation=ctx.opp_formation,
        matchup_vector=matchup_vector,
        matchup_advice=matchup_advice,
        set_piece_top=sp_top,
        threat_top_lane=threat_lane,
        threat_advice=threat_advice,
        headline=headline,
        plan_lines=tuple(plan_lines),
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="match",
        subject_id=0,
        metric="match_plan",
        value={
            "our_formation": ctx.our_formation,
            "opp_formation": ctx.opp_formation,
            "matchup_vector": matchup_vector,
            "set_piece_top_names": [p["name"] for p in sp_top],
            "threat_top_lane": threat_lane,
            "plan_line_count": len(plan_lines),
        },
        inputs={
            "opponent_style": ctx.opponent_style,
            "set_piece_type": ctx.set_piece_type,
            "sub_audits": {
                "formation_matchup": fmu.audit.value,
                "set_piece_library": sp.audit.value,
            },
        },
        formula=(
            "compose(formation_matchup) + compose(set_piece_library) + "
            "compose(threat_pathway?) → 1-sayfa plan"
        ),
    )
    return EngineResult(value=plan, audit=audit)
