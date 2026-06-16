"""Live Tactical Trigger — canlı taktiksel ayar tetikleri (Faz 6 #7, #8, #9).

Skor + dakika + momentum + rakip pattern'e göre üç canlı reçete:
1. Formation switch: "geride + 75. dk → daha hücumcu diziliş"
2. Press height: skor + yorgunluk → hattı yükselt/düşür
3. Hedef kanal kayması: rakip bir kanadı kapattıysa diğerine yük

Saf hesap. Skor/dakika/momentum/kanal verileri input.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.live_tactical_trigger"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class TacticalTrigger:
    trigger_type: str       # "formation" | "press_height" | "channel_shift"
    fired: bool
    recommendation: str
    urgency: str            # "high" | "medium" | "low"


@dataclass(frozen=True)
class LiveTacticalTriggerReport:
    team_external_id: int
    current_minute: float
    score_state: str        # "leading" | "level" | "trailing"
    triggers: tuple[TacticalTrigger, ...]   # fired olanlar önce
    active_count: int


def _score_state(my_score: int, opp_score: int) -> str:
    if my_score > opp_score:
        return "leading"
    if my_score < opp_score:
        return "trailing"
    return "level"


def _formation_trigger(
    state: str, minute: float, momentum: float,
) -> TacticalTrigger:
    if state == "trailing" and minute >= 70:
        return TacticalTrigger(
            "formation", True,
            "Geride + son 20 dk → 4-2-3-1 / 3-4-3 hücum dizilişi; ekstra forvet",
            "high",
        )
    if state == "leading" and minute >= 80 and momentum < -0.2:
        return TacticalTrigger(
            "formation", True,
            "Önde + rakip baskılı → 5-4-1 / 4-5-1 kapanma, sonucu koru",
            "medium",
        )
    return TacticalTrigger(
        "formation", False, "Diziliş değişikliği gerekmiyor", "low",
    )


def _press_height_trigger(
    state: str, avg_team_fatigue: float, momentum: float,
) -> TacticalTrigger:
    if avg_team_fatigue >= 0.55:
        return TacticalTrigger(
            "press_height", True,
            "Yüksek yorgunluk → pres hattını düşür, blok kompaktlığını koru",
            "high",
        )
    if state == "trailing" and momentum > -0.1:
        return TacticalTrigger(
            "press_height", True,
            "Geride + enerji var → pres hattını yükselt, rakip çıkışı boğ",
            "medium",
        )
    if state == "leading" and momentum < -0.3:
        return TacticalTrigger(
            "press_height", True,
            "Önde + rakip baskılı → orta blok'a çekil, kontra için alan bırak",
            "medium",
        )
    return TacticalTrigger(
        "press_height", False, "Pres yüksekliği uygun", "low",
    )


def _channel_shift_trigger(
    our_dominant_channel: str, opp_strong_channel: str,
) -> TacticalTrigger:
    """Bizim yüklendiğimiz kanal rakibin güçlü olduğu kanalsa → kaydır."""
    if our_dominant_channel == opp_strong_channel and our_dominant_channel != "balanced":
        other = {"left": "sağ kanat", "right": "sol kanat",
                 "central": "kanatlar"}.get(our_dominant_channel, "diğer kanal")
        return TacticalTrigger(
            "channel_shift", True,
            f"Rakip {our_dominant_channel} kanadını kapatıyor → {other}'a yük kaydır",
            "medium",
        )
    return TacticalTrigger(
        "channel_shift", False, "Kanal dağılımı uygun", "low",
    )


def compute_live_tactical_trigger(
    team_external_id: int,
    *,
    current_minute: float,
    my_score: int = 0,
    opponent_score: int = 0,
    momentum_score: float = 0.0,
    avg_team_fatigue: float = 0.0,
    our_dominant_channel: str = "balanced",
    opp_strong_channel: str = "balanced",
) -> EngineResult[LiveTacticalTriggerReport]:
    """Skor + dakika + momentum + kanal → taktiksel tetikler."""
    state = _score_state(my_score, opponent_score)
    triggers = [
        _formation_trigger(state, current_minute, momentum_score),
        _press_height_trigger(state, avg_team_fatigue, momentum_score),
        _channel_shift_trigger(our_dominant_channel, opp_strong_channel),
    ]
    # Fired olanlar önce + urgency
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    triggers.sort(key=lambda t: (not t.fired, urgency_order.get(t.urgency, 9)))
    active = sum(1 for t in triggers if t.fired)

    report = LiveTacticalTriggerReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        score_state=state,
        triggers=tuple(triggers),
        active_count=active,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="live_tactical_trigger",
        value={
            "score_state": state, "active_count": active,
            "triggers": [
                {"type": t.trigger_type, "fired": t.fired,
                 "urgency": t.urgency, "recommendation": t.recommendation}
                for t in triggers
            ],
        },
        inputs={
            "current_minute": current_minute,
            "my_score": my_score, "opponent_score": opponent_score,
            "momentum_score": momentum_score,
            "avg_team_fatigue": avg_team_fatigue,
            "our_dominant_channel": our_dominant_channel,
            "opp_strong_channel": opp_strong_channel,
        },
        formula="skor+dakika→formation; fatigue+momentum→press; kanal çakışması→shift",
    )
    return EngineResult(value=report, audit=audit)
