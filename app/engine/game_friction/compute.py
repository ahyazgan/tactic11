"""Game Friction — sürtünme / oyun yönetimi (Faz 7 I: #9, #10).

İki sinyal:
9. Faul biriktirme: rakip belirli bir bölgede tekrar tekrar faul yapıyor →
   "oraya koşu yap, serbest vuruş kazan" (payload: opponent_foul_zones).
10. Ofsayt tuzağı: rakibin defansif hattı yüksek + senkron → derin pas riski/
    fırsatı (event proxy: rakip def aksiyon ortalama x'i yüksek + dar bant).

Saf hesap. Def listesi + window + (opsiyonel opponent_foul_zones).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction

ENGINE_NAME = "engine.game_friction"
ENGINE_VERSION = "1"

WINDOW_MIN = 15.0
# Faul biriktirme: aynı zonda >= bu kadar faul
FOUL_ZONE_MIN = 2
# Ofsayt tuzağı: rakip hat x ortalaması (bizim hücum yönü, 100-x) >= bu
HIGH_LINE_X = 65.0
# + hat senkronu: x std bu kadarın altında (dar = senkron)
LINE_SYNC_STD = 10.0
# Anlamlı örneklem
LINE_MIN_ACTIONS = 4


@dataclass(frozen=True)
class FoulHotspot:
    zone: str
    count: int


@dataclass(frozen=True)
class GameFrictionReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    window_min: float
    # #9 faul biriktirme
    foul_hotspot: FoulHotspot | None
    # #10 ofsayt tuzağı
    offside_trap_risk: bool
    opp_line_height: float
    opp_line_sync_std: float
    alerts: tuple[str, ...] = field(default_factory=tuple)


def compute_game_friction(
    team_external_id: int,
    opponent_external_id: int,
    defs: list[DefensiveAction],
    *,
    current_minute: float,
    window_min: float = WINDOW_MIN,
    opponent_foul_zones: list[str] | None = None,
) -> EngineResult[GameFrictionReport]:
    win_start = current_minute - window_min
    in_win = lambda m: win_start <= m <= current_minute  # noqa: E731

    # #9 faul biriktirme — payload zon listesi
    hotspot: FoulHotspot | None = None
    if opponent_foul_zones:
        counts: dict[str, int] = {}
        for z in opponent_foul_zones:
            counts[z] = counts.get(z, 0) + 1
        zone, cnt = max(counts.items(), key=lambda kv: kv[1])
        if cnt >= FOUL_ZONE_MIN:
            hotspot = FoulHotspot(zone, cnt)

    # #10 ofsayt tuzağı — rakip defansif hat yüksekliği + senkron
    opp_d = [d for d in defs if d.team_external_id == opponent_external_id
             and in_win(d.minute)]
    # Bizim hücum yönümüze çevir: x=100 bizim attack goal; rakip def x'i ayna
    line_xs = [100.0 - d.x for d in opp_d]
    line_height = statistics.fmean(line_xs) if line_xs else 0.0
    line_std = statistics.pstdev(line_xs) if len(line_xs) >= 2 else 99.0
    trap_risk = (
        len(opp_d) >= LINE_MIN_ACTIONS
        and line_height >= HIGH_LINE_X
        and line_std <= LINE_SYNC_STD
    )

    alerts: list[str] = []
    if hotspot:
        alerts.append(
            f"FAUL BÖLGESİ: rakip {hotspot.zone} bölgesinde {hotspot.count} faul "
            "— oraya koşu yap, serbest vuruş kazan"
        )
    if trap_risk:
        alerts.append(
            f"OFSAYT TUZAĞI: rakip yüksek + senkron hat (x≈{line_height:.0f}, "
            f"std {line_std:.0f}) — derin pas riski, zamanlamaya dikkat"
        )

    report = GameFrictionReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        window_min=window_min,
        foul_hotspot=hotspot,
        offside_trap_risk=trap_risk,
        opp_line_height=round(line_height, 2),
        opp_line_sync_std=round(line_std, 2),
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="game_friction",
        value={
            "foul_hotspot": hotspot.zone if hotspot else None,
            "offside_trap_risk": trap_risk, "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute, "window_min": window_min,
            "opponent_external_id": opponent_external_id,
            "opponent_foul_zones": opponent_foul_zones,
        },
        formula="zon faul sayımı; rakip def hat x ortalaması + senkron std → ofsayt tuzağı",
    )
    return EngineResult(value=report, audit=audit)
