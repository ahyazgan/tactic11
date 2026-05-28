"""Passes Per Defensive Action (PPDA) — pres yoğunluğu ölçüsü.

Tanım: rakibin **savunma yarısı dışında** (yani saha x ≥ 40) yaptığı pas
sayısı bölü takımın savunma yarısı dışında yaptığı defansif aksiyon sayısı.

Düşük PPDA = yoğun pres (Klopp Liverpool ~8). Yüksek PPDA = düşük blok
(parke takımlar ~15-18).

Saf hesap. PassEvent + DefensiveAction listelerinden iki rakam üretir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.ppda"
ENGINE_VERSION = "1"

# Pres bölgesi: takımın hücum tarafından geçen pasları + defansif aksiyonları.
# Standart literatür: opp_half = x ≥ 40 (saha 100×100 normalize'da %60'lık
# hücum bölgesi). Bu eşik literatür ortalaması; futbol uzmanları %50-66 arası
# kullanır.
PRESS_ZONE_X_MIN = 40.0


@dataclass(frozen=True)
class PPDAReport:
    team_external_id: int
    matches_analyzed: int
    opp_passes_in_press_zone: int
    team_def_actions_in_press_zone: int
    ppda: float  # passes / def_actions; düşük = yoğun pres


def compute_ppda(
    team_external_id: int,
    all_passes: Iterable[PassEvent],
    all_def_actions: Iterable[DefensiveAction],
    *,
    matches_analyzed: int = 1,
) -> EngineResult[PPDAReport]:
    """Bir takımın PPDA değeri.

    Args:
        team_external_id: bizim takım
        all_passes: TÜM oyuncuların pasları (rakibinki dahil)
        all_def_actions: TÜM oyuncuların defansif aksiyonları
        matches_analyzed: kaç maç birleştirildi (raporlama için)

    Pres zone: opponent_passes.start_x ≥ PRESS_ZONE_X_MIN için sayılır
    (rakip hücum yarısına geçen paslar) ve team_def_actions.x ≥
    PRESS_ZONE_X_MIN (bizim hücum yarısında yapılan defansif aksiyonlar).
    """
    opp_passes = 0
    for p in all_passes:
        if p.team_external_id == team_external_id:
            continue  # bizim paslar
        if p.start_x < PRESS_ZONE_X_MIN:
            continue
        opp_passes += 1

    team_actions = 0
    for d in all_def_actions:
        if d.team_external_id != team_external_id:
            continue
        if d.x < PRESS_ZONE_X_MIN:
            continue
        team_actions += 1

    ppda_value = opp_passes / team_actions if team_actions > 0 else float("inf")
    if ppda_value == float("inf"):
        ppda_value = 999.0  # JSON-serializable

    report = PPDAReport(
        team_external_id=team_external_id,
        matches_analyzed=matches_analyzed,
        opp_passes_in_press_zone=opp_passes,
        team_def_actions_in_press_zone=team_actions,
        ppda=round(ppda_value, 2),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="team_ppda",
        value={
            "opp_passes_in_press_zone": opp_passes,
            "team_def_actions_in_press_zone": team_actions,
            "ppda": report.ppda,
            "matches_analyzed": matches_analyzed,
        },
        inputs={
            "press_zone_x_min": PRESS_ZONE_X_MIN,
        },
        formula=(
            f"opp_passes (x ≥ {PRESS_ZONE_X_MIN}) / "
            f"team_def_actions (x ≥ {PRESS_ZONE_X_MIN})"
        ),
    )
    return EngineResult(value=report, audit=audit)
