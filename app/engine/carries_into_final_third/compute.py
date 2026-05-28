"""Carries Into Final Third — savunma yarısından son üçe taşımalar.

Tanım: bir Carry "savunma yarısı 'na (x < 50) bağlıdır VE bitişi hücum
üçündedir (x ≥ 66.7). Klassik ball-carrier metriği (De Bruyne, Trent).

Saf hesap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import Carry

ENGINE_NAME = "engine.carries_into_final_third"
ENGINE_VERSION = "1"

OWN_HALF_MAX = 50.0
FINAL_THIRD_MIN = 66.7


@dataclass(frozen=True)
class CarriesIntoFinalThirdReport:
    player_external_id: int | None
    team_external_id: int | None
    matches_analyzed: int
    player_minutes_played: float | None
    total_carries: int
    deep_to_final_third: int     # savunma yarısı → son 1/3
    per_90: float | None


def _is_carry_into_final_third(c: Carry) -> bool:
    return c.start_x < OWN_HALF_MAX and c.end_x >= FINAL_THIRD_MIN


def compute_carries_into_final_third(
    *,
    team_external_id: int | None = None,
    player_external_id: int | None = None,
    all_carries: Iterable[Carry],
    player_minutes_played: float | None = None,
    matches_analyzed: int = 1,
) -> EngineResult[CarriesIntoFinalThirdReport]:
    if team_external_id is None and player_external_id is None:
        raise ValueError("team_external_id veya player_external_id verilmeli")

    def _match(c: Carry) -> bool:
        if player_external_id is not None:
            return c.player_external_id == player_external_id
        return c.team_external_id == team_external_id

    subject = [c for c in all_carries if _match(c)]
    deep_run = [c for c in subject if _is_carry_into_final_third(c)]

    per_90: float | None = None
    if player_external_id is not None and player_minutes_played and player_minutes_played > 0:
        per_90 = round((len(deep_run) / player_minutes_played) * 90, 2)

    report = CarriesIntoFinalThirdReport(
        player_external_id=player_external_id,
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        player_minutes_played=player_minutes_played,
        total_carries=len(subject),
        deep_to_final_third=len(deep_run),
        per_90=per_90,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player" if player_external_id else "team",
        subject_id=player_external_id or team_external_id or 0,
        metric="carries_into_final_third",
        value={
            "total_carries": report.total_carries,
            "deep_to_final_third": report.deep_to_final_third,
            "per_90": report.per_90,
        },
        inputs={
            "own_half_max": OWN_HALF_MAX,
            "final_third_min": FINAL_THIRD_MIN,
            "matches_analyzed": matches_analyzed,
        },
        formula="count carries with start_x<50 AND end_x>=66.7",
    )
    return EngineResult(value=report, audit=audit)
