"""Live Risk Monitor — kart/sakatlık/zaman riski (Faz 6 #10, #11, #12).

Üç canlı risk sinyali:
1. Kart riski: sarı kartlı + yüksek düello yapan oyuncu → değiştir/uyar
2. Anlık sakatlık riski: yorgunluk eşiği aşan oyuncu sahada → flag
3. Zaman yönetimi: öndeyken "beklet" / geride "tempoyu artır" reçetesi

Saf hesap. Oyuncu durum listesi + skor + dakika input.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.live_risk_monitor"
ENGINE_VERSION = "1"

# Yüksek düello eşiği (kart riski) — bu maçta yapılan düello sayısı
HIGH_DUEL_COUNT = 4
# Sakatlık flag fatigue eşiği
INJURY_FATIGUE_THRESHOLD = 0.65


@dataclass(frozen=True)
class PlayerRiskFlag:
    player_external_id: int
    risk_type: str          # "card" | "injury"
    severity: str           # "high" | "medium"
    message: str


@dataclass(frozen=True)
class LiveRiskReport:
    team_external_id: int
    current_minute: float
    score_state: str
    card_flags: tuple[PlayerRiskFlag, ...]
    injury_flags: tuple[PlayerRiskFlag, ...]
    time_management: str    # zaman yönetimi reçetesi
    total_flags: int


def _score_state(my_score: int, opp_score: int) -> str:
    if my_score > opp_score:
        return "leading"
    if my_score < opp_score:
        return "trailing"
    return "level"


def _time_management(state: str, minute: float) -> str:
    if minute < 70:
        return "Normal tempo — henüz zaman yönetimi devreye girmedi"
    if state == "leading":
        return (
            "Öndeyiz + son 20 dk → topu beklet, oyunu yavaşlat, "
            "köşe/taç uzat, riskli pas yapma"
        )
    if state == "trailing":
        return (
            "Geride + son 20 dk → tempoyu artır, hızlı restart, "
            "direkt oyun, riski göze al"
        )
    return "Berabere + son dakikalar → dengeli; kazanma fırsatı kolla"


def compute_live_risk_monitor(
    team_external_id: int,
    player_states: Iterable[dict[str, Any]],
    *,
    current_minute: float,
    my_score: int = 0,
    opponent_score: int = 0,
) -> EngineResult[LiveRiskReport]:
    """Kart + sakatlık + zaman riski.

    player_states: [{player_id, yellow_card?, duel_count?, fatigue?}]
    """
    state = _score_state(my_score, opponent_score)
    card_flags: list[PlayerRiskFlag] = []
    injury_flags: list[PlayerRiskFlag] = []

    for ps in player_states:
        pid = ps.get("player_id", 0)
        yellow = ps.get("yellow_card", False)
        duels = ps.get("duel_count", 0)
        fatigue = ps.get("fatigue", 0.0)

        # Kart riski: sarılı + agresif düello
        if yellow and duels >= HIGH_DUEL_COUNT:
            card_flags.append(PlayerRiskFlag(
                player_external_id=pid, risk_type="card",
                severity="high",
                message=(
                    f"Player {pid} sarı kartlı + {duels} düello — "
                    f"ikinci sarı riski, değiştir ya da uyar"
                ),
            ))
        elif yellow and duels >= HIGH_DUEL_COUNT - 1:
            card_flags.append(PlayerRiskFlag(
                player_external_id=pid, risk_type="card",
                severity="medium",
                message=f"Player {pid} sarı kartlı — agresif girişlere dikkat",
            ))

        # Sakatlık riski: fatigue eşiği
        if fatigue >= INJURY_FATIGUE_THRESHOLD:
            injury_flags.append(PlayerRiskFlag(
                player_external_id=pid, risk_type="injury",
                severity="high" if fatigue >= 0.8 else "medium",
                message=(
                    f"Player {pid} yorgunluk {fatigue:.2f} — "
                    f"sakatlık riski, değişiklik düşün"
                ),
            ))

    report = LiveRiskReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        score_state=state,
        card_flags=tuple(card_flags),
        injury_flags=tuple(injury_flags),
        time_management=_time_management(state, current_minute),
        total_flags=len(card_flags) + len(injury_flags),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="live_risk_monitor",
        value={
            "score_state": state,
            "total_flags": report.total_flags,
            "card_flags": [
                {"player_id": f.player_external_id, "severity": f.severity,
                 "message": f.message}
                for f in card_flags
            ],
            "injury_flags": [
                {"player_id": f.player_external_id, "severity": f.severity,
                 "message": f.message}
                for f in injury_flags
            ],
            "time_management": report.time_management,
        },
        inputs={
            "current_minute": current_minute,
            "my_score": my_score, "opponent_score": opponent_score,
            "high_duel_count": HIGH_DUEL_COUNT,
            "injury_fatigue_threshold": INJURY_FATIGUE_THRESHOLD,
        },
        formula="sarı+düello≥4→kart; fatigue≥0.65→sakatlık; skor+dakika→zaman yönetimi",
    )
    return EngineResult(value=report, audit=audit)
