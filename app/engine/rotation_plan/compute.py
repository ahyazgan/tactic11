"""Rotation Plan — yük periyotlama / rotasyon önerisi (Faz 5 #31).

Yoğun fikstür periyodunda hangi oyuncuların dinlendirilmesi gerektiğini,
sıradaki maçlar için rotasyon önerisini hesaplar.

Girdi: oyuncu yük raporları + sıradaki maç sayısı/yoğunluğu.
Çıktı: dinlendirilmesi önerilen oyuncular + rotasyon yoğunluğu önerisi.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.rotation_plan"
ENGINE_VERSION = "1"

# Rotasyon öncelik eşiği — risk_level
ROTATE_RISK_LEVELS = ("high", "extreme")


@dataclass(frozen=True)
class RotationCandidate:
    player_external_id: int
    risk_level: str
    minutes_per_week: float
    rest_priority: int          # 1 = en acil dinlendir
    reason: str


@dataclass(frozen=True)
class RotationPlanReport:
    team_external_id: int
    upcoming_matches: int
    dense_schedule: bool
    rotate_count: int           # dinlendirilmesi önerilen oyuncu
    candidates: tuple[RotationCandidate, ...]   # rest_priority sıralı
    rotation_intensity: str     # "minimal" | "moderate" | "aggressive"


def _intensity(rotate_count: int, dense: bool, upcoming: int) -> str:
    if dense and rotate_count >= 4:
        return "aggressive"
    if rotate_count >= 2 or (dense and upcoming >= 3):
        return "moderate"
    return "minimal"


def compute_rotation_plan(
    team_external_id: int,
    player_loads: Iterable[dict[str, Any]],
    *,
    upcoming_matches: int = 0,
    dense_schedule: bool = False,
) -> EngineResult[RotationPlanReport]:
    """Yük + fikstür yoğunluğundan rotasyon önerisi.

    player_loads: [{player_external_id, risk_level, minutes_per_week,
                    back_to_back_count}]
    """
    candidates: list[RotationCandidate] = []
    for pl in player_loads:
        risk = pl.get("risk_level", "low")
        mpw = pl.get("minutes_per_week", 0.0)
        b2b = pl.get("back_to_back_count", 0)
        if risk not in ROTATE_RISK_LEVELS:
            continue
        # rest_priority: extreme + yüksek b2b = en acil
        priority_score = (
            (2 if risk == "extreme" else 1) * 100 + mpw + b2b * 20
        )
        reason_parts = [f"risk {risk}", f"{mpw:.0f} dk/hafta"]
        if b2b >= 3:
            reason_parts.append(f"{b2b} maç/5g")
        candidates.append(RotationCandidate(
            player_external_id=pl.get("player_external_id", 0),
            risk_level=risk,
            minutes_per_week=mpw,
            rest_priority=int(priority_score),  # geçici, aşağıda sıralanır
            reason=", ".join(reason_parts),
        ))

    # Priority score'a göre sırala, 1-indexed rest_priority ata
    candidates.sort(key=lambda c: -c.rest_priority)
    ranked = tuple(
        RotationCandidate(
            player_external_id=c.player_external_id,
            risk_level=c.risk_level,
            minutes_per_week=c.minutes_per_week,
            rest_priority=i + 1,
            reason=c.reason,
        )
        for i, c in enumerate(candidates)
    )

    report = RotationPlanReport(
        team_external_id=team_external_id,
        upcoming_matches=upcoming_matches,
        dense_schedule=dense_schedule,
        rotate_count=len(ranked),
        candidates=ranked,
        rotation_intensity=_intensity(len(ranked), dense_schedule, upcoming_matches),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="rotation_plan",
        value={
            "rotate_count": len(ranked),
            "rotation_intensity": report.rotation_intensity,
            "upcoming_matches": upcoming_matches,
            "dense_schedule": dense_schedule,
            "candidates": [
                {"player_id": c.player_external_id, "priority": c.rest_priority,
                 "risk": c.risk_level, "reason": c.reason}
                for c in ranked
            ],
        },
        inputs={
            "rotate_risk_levels": list(ROTATE_RISK_LEVELS),
            "upcoming_matches": upcoming_matches,
            "dense_schedule": dense_schedule,
        },
        formula="high/extreme risk oyuncular → rest_priority (extreme×2 + mpw + b2b)",
    )
    return EngineResult(value=report, audit=audit)
