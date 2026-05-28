"""Defensive Duels Won % — yer düellosu kazanma oranı.

StatsBomb 'Duel' eventi outcome.name 'Won'/'Lost' içerir. Bizim
DefensiveAction modelinde `action_type=tackle` ve `successful=True` → won
sayılıyor. Bu engine takım VEYA oyuncu için duel-won oranını döner.

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction

ENGINE_NAME = "engine.defensive_duels"
ENGINE_VERSION = "1"

DUEL_ACTIONS = ("tackle", "duel_won")


@dataclass(frozen=True)
class DefensiveDuelsReport:
    team_external_id: int | None
    player_external_id: int | None
    matches_analyzed: int
    total_duels: int
    duels_won: int
    win_rate: float


def compute_defensive_duels(
    *,
    team_external_id: int | None = None,
    player_external_id: int | None = None,
    all_def_actions: Iterable[DefensiveAction],
    matches_analyzed: int = 1,
) -> EngineResult[DefensiveDuelsReport]:
    if team_external_id is None and player_external_id is None:
        raise ValueError("team_external_id veya player_external_id verilmeli")

    def _match(d: DefensiveAction) -> bool:
        if player_external_id is not None:
            return d.player_external_id == player_external_id
        return d.team_external_id == team_external_id

    duels = [d for d in all_def_actions if _match(d) and d.action_type in DUEL_ACTIONS]
    won = sum(1 for d in duels if d.successful)
    total = len(duels)

    report = DefensiveDuelsReport(
        team_external_id=team_external_id,
        player_external_id=player_external_id,
        matches_analyzed=matches_analyzed,
        total_duels=total,
        duels_won=won,
        win_rate=round(won / total, 3) if total else 0.0,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player" if player_external_id else "team",
        subject_id=player_external_id or team_external_id or 0,
        metric="defensive_duels_won",
        value={"total_duels": total, "duels_won": won, "win_rate": report.win_rate},
        inputs={"duel_actions": list(DUEL_ACTIONS), "matches_analyzed": matches_analyzed},
        formula="won/total for action_type in (tackle, duel_won)",
    )
    return EngineResult(value=report, audit=audit)
