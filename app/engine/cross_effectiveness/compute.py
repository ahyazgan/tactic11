"""Cross Effectiveness — orta vuruş tipi × varış zone × şut sonucu.

Wyscout/Opta brief'leri ortaların etkinliğini "tip × zone × sonuç" üçlüsünde
analiz eder. Bu modül:
- Cross paslarının (`pass_type=cross`) bittiği zone (near_post/central/far_post)
- O cross'tan hemen sonra (≤6 saniye) gelen şut + xG/goal sonucu

Saf hesap. PassEvent + Shot listeleriyle çalışır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot

ENGINE_NAME = "engine.cross_effectiveness"
ENGINE_VERSION = "1"

# Şut-eşleştirme zaman penceresi (dk)
CROSS_TO_SHOT_WINDOW = 0.10  # 6 saniye


def _zone_for(y: float) -> str:
    if y < 33.3:
        return "near_post"
    if y > 66.7:
        return "far_post"
    return "central"


@dataclass(frozen=True)
class CrossZoneStats:
    zone: str
    crosses: int
    shots_resulted: int
    goals_resulted: int
    shot_conversion: float
    goal_conversion: float


@dataclass(frozen=True)
class CrossEffectivenessReport:
    team_external_id: int
    matches_analyzed: int
    total_crosses: int
    completed_crosses: int
    completion_rate: float
    shots_from_crosses: int
    goals_from_crosses: int
    by_zone: tuple[CrossZoneStats, ...]
    most_effective_zone: str


def compute_cross_effectiveness(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_shots: Iterable[Shot],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[CrossEffectivenessReport]:
    crosses = [
        p for p in all_passes
        if p.team_external_id == team_external_id and p.pass_type == "cross"
    ]
    shots = sorted(all_shots, key=lambda s: s.minute)

    zone_counts: dict[str, dict[str, int]] = {
        z: {"crosses": 0, "shots": 0, "goals": 0}
        for z in ("near_post", "central", "far_post")
    }
    shots_total = 0
    goals_total = 0
    completed = 0

    for c in crosses:
        if c.completed:
            completed += 1
        z = _zone_for(c.end_y)
        zone_counts[z]["crosses"] += 1
        # Şut eşleştirme: cross.minute'dan sonra <=window içinde şut
        for s in shots:
            if s.minute < c.minute:
                continue
            if s.minute - c.minute > CROSS_TO_SHOT_WINDOW:
                break
            shots_total += 1
            zone_counts[z]["shots"] += 1
            if s.is_goal:
                goals_total += 1
                zone_counts[z]["goals"] += 1
            break

    by_zone = tuple(
        CrossZoneStats(
            zone=z,
            crosses=c["crosses"],
            shots_resulted=c["shots"],
            goals_resulted=c["goals"],
            shot_conversion=round(c["shots"] / c["crosses"], 3) if c["crosses"] else 0.0,
            goal_conversion=round(c["goals"] / c["crosses"], 3) if c["crosses"] else 0.0,
        )
        for z, c in zone_counts.items()
    )
    most_eff = (
        max(by_zone, key=lambda z: (z.goal_conversion, z.shot_conversion, z.crosses)).zone
        if crosses else "insufficient_data"
    )

    report = CrossEffectivenessReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        total_crosses=len(crosses),
        completed_crosses=completed,
        completion_rate=round(completed / len(crosses), 3) if crosses else 0.0,
        shots_from_crosses=shots_total,
        goals_from_crosses=goals_total,
        by_zone=by_zone,
        most_effective_zone=most_eff,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="cross_effectiveness",
        value={
            "total_crosses": report.total_crosses,
            "shots_from_crosses": shots_total,
            "goals_from_crosses": goals_total,
            "most_effective_zone": report.most_effective_zone,
        },
        inputs={
            "cross_to_shot_window_min": CROSS_TO_SHOT_WINDOW,
            "matches_analyzed": matches_analyzed,
        },
        formula="filter cross passes; bin by end_y zone; pair with shot in window",
    )
    return EngineResult(value=report, audit=audit)
