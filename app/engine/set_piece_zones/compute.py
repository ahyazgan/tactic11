"""Set-piece Zone Heatmap — duran top kaynaklı şutların bölge dağılımı.

Mevcut `engine.set_piece` set-piece sayım + xG verir; bu engine daha
derin: kalenin önünde **5 bölge** (6-yarda kutusu solu/ortası/sağı +
6-18-yarda hattı + 18+) tehditten haritalar.

Tanım: bir takımın yediği/attığı set-piece şutlarının (corner_kick,
free_kick, set_piece) x-y koordinat bantlarına dağılımı.

Bölgeler (saha 100×100, kale x=100):
- z1 "near_post":   x ≥ 90, y < 33
- z2 "central_6yd": x ≥ 95, 33 ≤ y ≤ 67
- z3 "far_post":    x ≥ 90, y > 67
- z4 "penalty_arc": 80 ≤ x < 90 (any y)
- z5 "outside_box": x < 80

Saf hesap. Shot listesi → SetPieceZoneReport.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Shot
from app.engine.set_piece.compute import SET_PIECE_PATTERNS

ENGINE_NAME = "engine.set_piece_zones"
ENGINE_VERSION = "1"


def _zone_for(x: float, y: float) -> str:
    if x < 80:
        return "outside_box"
    if x >= 95 and 33.3 <= y <= 66.7:
        return "central_6yd"
    if x >= 90 and y < 33.3:
        return "near_post"
    if x >= 90 and y > 66.7:
        return "far_post"
    return "penalty_arc"


@dataclass(frozen=True)
class ZoneStats:
    zone: str
    shots: int
    goals: int
    conversion_rate: float


@dataclass(frozen=True)
class SetPieceZoneReport:
    team_external_id: int
    role: str                       # "offensive" | "defensive"
    set_piece_type: str             # "all" | "corner_kick" | "free_kick" | "set_piece"
    matches_analyzed: int
    total_shots: int
    total_goals: int
    zones: tuple[ZoneStats, ...]    # 5 bölge
    most_threatening_zone: str      # en yüksek conversion (eşitlikte en çok şut)


def compute_set_piece_zones(
    team_external_id: int,
    shots: Iterable[Shot],
    *,
    role: str = "offensive",
    set_piece_type: str = "all",
    matches_analyzed: int = 1,
) -> EngineResult[SetPieceZoneReport]:
    if role not in ("offensive", "defensive"):
        raise ValueError(f"role 'offensive'|'defensive' olmalı: {role!r}")

    relevant = []
    for s in shots:
        if s.pattern not in SET_PIECE_PATTERNS:
            continue
        if set_piece_type != "all" and s.pattern != set_piece_type:
            continue
        relevant.append(s)

    counts: dict[str, dict[str, int]] = {
        z: {"shots": 0, "goals": 0}
        for z in ("near_post", "central_6yd", "far_post", "penalty_arc", "outside_box")
    }
    for s in relevant:
        z = _zone_for(s.x, s.y)
        counts[z]["shots"] += 1
        if s.is_goal:
            counts[z]["goals"] += 1

    zones = tuple(
        ZoneStats(
            zone=z,
            shots=c["shots"],
            goals=c["goals"],
            conversion_rate=round(c["goals"] / c["shots"], 4) if c["shots"] else 0.0,
        )
        for z, c in counts.items()
    )
    # En tehlikeli zone: conversion en yüksek; eşit ise shots en çok
    most_threat = max(
        zones, key=lambda z: (z.conversion_rate, z.shots),
    ).zone if relevant else "insufficient_data"

    report = SetPieceZoneReport(
        team_external_id=team_external_id,
        role=role,
        set_piece_type=set_piece_type,
        matches_analyzed=matches_analyzed,
        total_shots=len(relevant),
        total_goals=sum(1 for s in relevant if s.is_goal),
        zones=zones,
        most_threatening_zone=most_threat,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="set_piece_zones",
        value={
            "total_shots": report.total_shots,
            "total_goals": report.total_goals,
            "most_threatening_zone": report.most_threatening_zone,
            "zone_breakdown": [
                {"zone": z.zone, "shots": z.shots, "goals": z.goals, "conv": z.conversion_rate}
                for z in zones
            ],
        },
        inputs={
            "role": role,
            "set_piece_type": set_piece_type,
            "matches_analyzed": matches_analyzed,
        },
        formula="bin set-piece shots by 5 zones; conversion = goals/shots per zone",
    )
    return EngineResult(value=report, audit=audit)
