"""Available Squad — müsait kadro ön-filtresi (Faz 5 #23).

Maç öncesi: "kim oynayabilir?" Sakatlık + kart cezası + aşırı yük
filtresinden geçen müsait oyuncu listesi + neden-elendi raporu.

Saf hesap. Caller squad listesi + status bilgisi gönderir:
[{player_id, position?, injured?, suspended?, risk_level?}]

Çıktı:
- available: oynayabilir
- doubtful: yüksek yük (oynar ama risk)
- unavailable: sakat/cezalı + sebep
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.available_squad"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class PlayerAvailability:
    player_external_id: int
    position: str | None
    status: str            # "available" | "doubtful" | "unavailable"
    reason: str | None     # neden doubtful/unavailable
    risk_level: str | None


@dataclass(frozen=True)
class AvailableSquadReport:
    team_external_id: int
    total_squad: int
    available_count: int
    doubtful_count: int
    unavailable_count: int
    players: tuple[PlayerAvailability, ...]


def _classify(player: dict[str, Any]) -> PlayerAvailability:
    pid = player.get("player_id", 0)
    pos = player.get("position")
    risk = player.get("risk_level")
    if player.get("injured"):
        return PlayerAvailability(
            player_external_id=pid, position=pos,
            status="unavailable", reason="sakat", risk_level=risk,
        )
    if player.get("suspended"):
        return PlayerAvailability(
            player_external_id=pid, position=pos,
            status="unavailable", reason="kart cezası", risk_level=risk,
        )
    if risk in ("high", "extreme"):
        return PlayerAvailability(
            player_external_id=pid, position=pos,
            status="doubtful",
            reason=f"yüksek yük ({risk})", risk_level=risk,
        )
    return PlayerAvailability(
        player_external_id=pid, position=pos,
        status="available", reason=None, risk_level=risk,
    )


def compute_available_squad(
    team_external_id: int,
    squad: Iterable[dict[str, Any]],
) -> EngineResult[AvailableSquadReport]:
    """Squad listesinden müsaitlik raporu.

    squad: [{player_id, position?, injured?, suspended?, risk_level?}]
    """
    classified = [_classify(p) for p in squad]
    avail = sum(1 for p in classified if p.status == "available")
    doubt = sum(1 for p in classified if p.status == "doubtful")
    unavail = sum(1 for p in classified if p.status == "unavailable")

    # Sıralama: available → doubtful → unavailable
    order = {"available": 0, "doubtful": 1, "unavailable": 2}
    classified.sort(key=lambda p: order.get(p.status, 9))

    report = AvailableSquadReport(
        team_external_id=team_external_id,
        total_squad=len(classified),
        available_count=avail,
        doubtful_count=doubt,
        unavailable_count=unavail,
        players=tuple(classified),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="available_squad",
        value={
            "total_squad": len(classified),
            "available_count": avail,
            "doubtful_count": doubt,
            "unavailable_count": unavail,
            "players": [
                {"player_id": p.player_external_id, "status": p.status,
                 "reason": p.reason, "position": p.position}
                for p in classified
            ],
        },
        inputs={"squad_size": len(classified)},
        formula="injured/suspended → unavailable; high/extreme load → doubtful; else available",
    )
    return EngineResult(value=report, audit=audit)
