"""Recovery Zone Heat — top kazanımlarının zone dağılımı.

Tanım: takımın `ball_recovery|tackle|interception` aksiyonlarının x-zonelara
göre yüzdesi:
- defensive_third: x < 33.3 (kendi savunma üçü)
- middle_third:    33.3 ≤ x < 66.7
- attacking_third: x ≥ 66.7 (rakip üçü — gegenpress göstergesi)

Yüksek attacking_third oranı = saldırgan-pres yapan takım (Klopp/Bielsa).
Yüksek defensive_third = derin blok (Mourinho-tarz).

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction

ENGINE_NAME = "engine.recovery_zone_heat"
ENGINE_VERSION = "1"

RECOVERY_ACTIONS = ("ball_recovery", "tackle", "interception")
DEFENSIVE_X_MAX = 33.3
ATTACKING_X_MIN = 66.7


@dataclass(frozen=True)
class RecoveryZoneHeatReport:
    team_external_id: int
    matches_analyzed: int
    total_recoveries: int
    defensive_third: int
    middle_third: int
    attacking_third: int
    defensive_share: float
    middle_share: float
    attacking_share: float
    style_label: str           # "high_press" | "mid_press" | "deep_block"


def _style(att_share: float, def_share: float) -> str:
    if att_share >= 0.35:
        return "high_press"
    if def_share >= 0.50:
        return "deep_block"
    return "mid_press"


def compute_recovery_zone_heat(
    team_external_id: int,
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[RecoveryZoneHeatReport]:
    recoveries = [
        d for d in all_def_actions
        if d.team_external_id == team_external_id and d.action_type in RECOVERY_ACTIONS
    ]
    if not recoveries:
        report = RecoveryZoneHeatReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            total_recoveries=0,
            defensive_third=0, middle_third=0, attacking_third=0,
            defensive_share=0.0, middle_share=0.0, attacking_share=0.0,
            style_label="insufficient_data",
        )
    else:
        d_third = sum(1 for d in recoveries if d.x < DEFENSIVE_X_MAX)
        a_third = sum(1 for d in recoveries if d.x >= ATTACKING_X_MIN)
        m_third = len(recoveries) - d_third - a_third
        n = len(recoveries)
        ds, ms, ats = d_third / n, m_third / n, a_third / n
        report = RecoveryZoneHeatReport(
            team_external_id=team_external_id,
            matches_analyzed=matches_analyzed,
            total_recoveries=n,
            defensive_third=d_third,
            middle_third=m_third,
            attacking_third=a_third,
            defensive_share=round(ds, 3),
            middle_share=round(ms, 3),
            attacking_share=round(ats, 3),
            style_label=_style(ats, ds),
        )

    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="recovery_zone_heat",
        value={
            "defensive_share": report.defensive_share,
            "middle_share": report.middle_share,
            "attacking_share": report.attacking_share,
            "style_label": report.style_label,
            "total_recoveries": report.total_recoveries,
        },
        inputs={
            "defensive_x_max": DEFENSIVE_X_MAX,
            "attacking_x_min": ATTACKING_X_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="bin recovery x into 3 thirds; style by att vs def share",
    )
    return EngineResult(value=report, audit=audit)
