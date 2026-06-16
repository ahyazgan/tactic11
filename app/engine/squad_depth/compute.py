"""Squad Depth — pozisyon bazlı kadro derinliği + yaşlanma (Faz 5 #33).

Her pozisyon (G/D/M/F) için: kaç oyuncu, ortalama yaş, yaşlanma riski
(çok yaşlı core + halef yok), derinlik durumu (yetersiz/yeterli/fazla).

Saf hesap. Caller squad listesi gönderir:
[{player_id, position, age?, minutes_season?}]
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult
from app.sports import football

ENGINE_NAME = "engine.squad_depth"
ENGINE_VERSION = "1"

# Pozisyon başına ideal minimum oyuncu (4-lü rotasyon mantığı)
MIN_PLAYERS_PER_POSITION = {
    football.POSITION_GOALKEEPER: 2,
    football.POSITION_DEFENDER: 6,
    football.POSITION_MIDFIELDER: 5,
    football.POSITION_FORWARD: 4,
}
AGING_THRESHOLD = 31


@dataclass(frozen=True)
class PositionDepth:
    position: str
    player_count: int
    avg_age: float | None
    aging_count: int            # yaş >= AGING_THRESHOLD
    min_required: int
    depth_status: str           # "insufficient" | "adequate" | "surplus"
    aging_risk: bool            # core yaşlı + derinlik az


@dataclass(frozen=True)
class SquadDepthReport:
    team_external_id: int
    total_players: int
    by_position: tuple[PositionDepth, ...]
    weakest_position: str       # en yetersiz derinlik
    aging_positions: tuple[str, ...]


def _depth_status(count: int, min_req: int) -> str:
    if count < min_req:
        return "insufficient"
    if count > min_req + 2:
        return "surplus"
    return "adequate"


def compute_squad_depth(
    team_external_id: int,
    squad: Iterable[dict[str, Any]],
) -> EngineResult[SquadDepthReport]:
    """Pozisyon bazlı derinlik + yaşlanma raporu.

    squad: [{player_id, position, age?}]
    position: G/D/M/F (football.POSITIONS)
    """
    by_pos: dict[str, list[dict[str, Any]]] = {
        p: [] for p in football.POSITIONS
    }
    for player in squad:
        pos = player.get("position")
        if pos in by_pos:
            by_pos[pos].append(player)

    positions: list[PositionDepth] = []
    aging_positions: list[str] = []
    for pos in football.POSITIONS:
        players = by_pos[pos]
        count = len(players)
        ages = [p["age"] for p in players if p.get("age") is not None]
        avg_age = round(sum(ages) / len(ages), 1) if ages else None
        aging_count = sum(1 for a in ages if a >= AGING_THRESHOLD)
        min_req = MIN_PLAYERS_PER_POSITION.get(pos, 3)
        status = _depth_status(count, min_req)
        # Yaşlanma riski: core'un yarısı+ yaşlı VE derinlik yetersiz/adequate
        aging_risk = (
            count > 0
            and aging_count / count >= 0.5
            and status != "surplus"
        )
        if aging_risk:
            aging_positions.append(pos)
        positions.append(PositionDepth(
            position=pos,
            player_count=count,
            avg_age=avg_age,
            aging_count=aging_count,
            min_required=min_req,
            depth_status=status,
            aging_risk=aging_risk,
        ))

    # En zayıf pozisyon: insufficient olanlardan en büyük açık
    insufficient = [
        p for p in positions if p.depth_status == "insufficient"
    ]
    if insufficient:
        weakest = min(
            insufficient, key=lambda p: p.player_count - p.min_required,
        ).position
    else:
        weakest = "none"

    report = SquadDepthReport(
        team_external_id=team_external_id,
        total_players=sum(p.player_count for p in positions),
        by_position=tuple(positions),
        weakest_position=weakest,
        aging_positions=tuple(aging_positions),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="squad_depth",
        value={
            "total_players": report.total_players,
            "weakest_position": weakest,
            "aging_positions": list(aging_positions),
            "by_position": [
                {"position": p.position, "count": p.player_count,
                 "avg_age": p.avg_age, "status": p.depth_status,
                 "aging_risk": p.aging_risk}
                for p in positions
            ],
        },
        inputs={
            "min_players_per_position": MIN_PLAYERS_PER_POSITION,
            "aging_threshold": AGING_THRESHOLD,
        },
        formula="pozisyon başına count vs min_required + yaşlanma (core yaş >= 31 oranı)",
    )
    return EngineResult(value=report, audit=audit)
