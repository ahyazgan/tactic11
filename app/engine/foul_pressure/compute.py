"""Foul Pressure — takım-düzeyi faul biriktirme + hakem kart eşiği (I kategorisi).

Üç maç-içi sinyal:
1. Rakip ritim-kırma fauluyor (son N dk yoğun ofansif faul) → hızlı restart
2. Bizim faul ritmimiz yüksek → savunmada agresif tackle azalt
3. Hakem kart eşiğine yaklaştı → temaslı presi düşür

Pure compute. Faul event listesi + opsiyonel oyuncu sarı durumu.
TD'nin "rakip bizi durdurmaya çalışıyor + savunmacımız 2. sarıya gidiyor"
sorusuna eşzamanlı cevap.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.foul_pressure"
ENGINE_VERSION = "1"

# Default pencere (dakika)
DEFAULT_WINDOW_MIN = 15.0
# Ritim kırma eşiği: rakip 3+ faul/10dk → tactical fouling alert
TACTICAL_FOULING_PER_10MIN = 3.0
# Bizim yüksek faul eşiği (kart riski) — 3+/10dk
OUR_HIGH_FOUL_PER_10MIN = 3.0
# Yığılma eşiği: rakip toplam faulun >%60'ı son window'da
ESCALATION_WINDOW_RATIO = 0.6
# Hakem kart eşiği — maç başına 6+ sarı yığını (her iki takım) → high
HIGH_REFEREE_CARD_THRESHOLD = 6
MODERATE_REFEREE_CARD_THRESHOLD = 4
# Oyuncu sarı + 3+ faul → critical (2. sarı yakın)
PLAYER_YELLOW_CRITICAL_FOULS = 3
PLAYER_NO_YELLOW_WARNING_FOULS = 4


@dataclass(frozen=True)
class FoulFlag:
    player_external_id: int
    fouls_committed: int
    has_yellow: bool
    risk_level: str       # "safe" | "warning" | "critical"
    message: str


@dataclass(frozen=True)
class FoulPressureReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    window_min: float
    # Takım-düzeyi
    our_fouls_total: int
    our_fouls_window: int
    opp_fouls_total: int
    opp_fouls_window: int
    our_foul_rate_per_10min: float
    opp_foul_rate_per_10min: float
    # Çağrışımlar
    tactical_fouling_alert: bool
    our_high_foul_alert: bool
    escalation_alert: bool
    # Oyuncu-düzeyi (sadece bizim takım)
    player_flags: tuple[FoulFlag, ...]
    # Hakem
    total_yellows_match: int
    referee_card_pressure: str    # "low" | "moderate" | "high"
    # Çıkarım
    tactical_advice: str


def _rate_per_10min(fouls: int, window: float) -> float:
    if window <= 0:
        return 0.0
    return round((fouls / window) * 10.0, 2)


def _referee_pressure(total_yellows: int) -> str:
    if total_yellows >= HIGH_REFEREE_CARD_THRESHOLD:
        return "high"
    if total_yellows >= MODERATE_REFEREE_CARD_THRESHOLD:
        return "moderate"
    return "low"


def _player_risk(fouls: int, has_yellow: bool) -> tuple[str, str]:
    """Oyuncu kart riski seviyesi + mesaj."""
    if has_yellow and fouls >= PLAYER_YELLOW_CRITICAL_FOULS:
        return "critical", (
            f"Sarı kartlı + {fouls} faul — 2. sarı çok yakın, "
            f"değiştir ya da kanat değiştir"
        )
    if has_yellow:
        return "warning", (
            f"Sarı kartlı, {fouls} faul yaptı — agresif girişten kaçındır"
        )
    if fouls >= PLAYER_NO_YELLOW_WARNING_FOULS:
        return "warning", (
            f"{fouls} faul yığdı — sarı yakın, savunmada zonal tut"
        )
    return "safe", ""


def _build_advice(
    *, opp_tactical: bool, our_high: bool, escalation: bool,
    ref_pressure: str,
) -> str:
    """Tek cümlelik tavsiye — TD'nin direkt aksiyon alacağı."""
    parts: list[str] = []
    if opp_tactical and escalation:
        parts.append(
            "Rakip ritim kırma fauluyor — hızlı restart al, "
            "faul olunca yere yatma, ayağa kalk"
        )
    elif opp_tactical:
        parts.append(
            "Rakip ofansif bölgemizde fauluyor — duran top fırsatına dön"
        )
    if our_high:
        parts.append(
            "Faul ritmimiz yüksek — savunmada zonal blok, agresif tackle azalt"
        )
    if ref_pressure == "high":
        parts.append(
            "Hakem kart eşiğinde — temaslı pres düşür, riski azalt"
        )
    if not parts:
        return "Faul ritmi normal — standart oyun planına devam"
    return " · ".join(parts)


def _ev_attrs(ev: Any) -> tuple[float, int, int | None, str | None]:
    """FoulEvent veya dict event → (minute, team_id, player_id, card).

    İki giriş şeklini destekle: domain.FoulEvent (typed) veya dict
    (eski payload-based endpoint için backward compat).
    """
    if hasattr(ev, "team_external_id"):
        return (
            float(ev.minute),
            int(ev.team_external_id),
            int(ev.player_external_id) if ev.player_external_id else None,
            ev.card,
        )
    minute = float(ev.get("minute", 0.0))
    team_id = int(ev.get("team_id", 0))
    pid = ev.get("player_id")
    pid_i = int(pid) if pid is not None else None
    card = ev.get("card")
    return minute, team_id, pid_i, card


def compute_foul_pressure(
    team_external_id: int,
    opponent_external_id: int,
    foul_events: Iterable[Any],
    *,
    current_minute: float,
    window_min: float = DEFAULT_WINDOW_MIN,
    player_yellow_cards: dict[int, int] | None = None,
    total_yellows_match: int | None = None,
) -> EngineResult[FoulPressureReport]:
    """Faul biriktirme + ritim kırma + hakem kart eşiği.

    foul_events: FoulEvent listesi VEYA dict listesi
                 [{minute, team_id, player_id?, card?}]
    player_yellow_cards: {player_id: yellow_count} — verilmezse event'lerden türetilir
    total_yellows_match: None verilirse event listesinden sayılır (otomatik)
    """
    yellow_states = dict(player_yellow_cards or {})
    auto_count_yellows = total_yellows_match is None
    total_yellows = 0 if auto_count_yellows else int(total_yellows_match)
    window_lo = current_minute - window_min

    # Takım-düzeyi sayım
    our_fouls_total = 0
    our_fouls_window = 0
    opp_fouls_total = 0
    opp_fouls_window = 0
    # Oyuncu-düzeyi sayım (sadece bizim takım)
    our_player_fouls: dict[int, int] = {}

    for ev in foul_events:
        minute, team_id, pid, card = _ev_attrs(ev)
        in_window = window_lo <= minute <= current_minute
        # Kart sayımı (her iki takım) — auto mode'da event'lerden hesapla
        if auto_count_yellows and card in ("yellow", "second_yellow", "red"):
            total_yellows += 1
        # Bizim takım oyuncusunun sarısını otomatik state'e ekle
        if (team_id == team_external_id and pid is not None
                and card in ("yellow", "second_yellow")
                and pid not in (player_yellow_cards or {})):
            yellow_states[pid] = yellow_states.get(pid, 0) + 1

        if team_id == team_external_id:
            our_fouls_total += 1
            if in_window:
                our_fouls_window += 1
            if pid is not None:
                our_player_fouls[pid] = our_player_fouls.get(pid, 0) + 1
        elif team_id == opponent_external_id:
            opp_fouls_total += 1
            if in_window:
                opp_fouls_window += 1
    total_yellows_match = total_yellows

    our_rate = _rate_per_10min(our_fouls_window, window_min)
    opp_rate = _rate_per_10min(opp_fouls_window, window_min)

    tactical_fouling = opp_rate >= TACTICAL_FOULING_PER_10MIN
    our_high_foul = our_rate >= OUR_HIGH_FOUL_PER_10MIN
    escalation = (
        opp_fouls_total > 0
        and (opp_fouls_window / opp_fouls_total) >= ESCALATION_WINDOW_RATIO
        and opp_fouls_window >= 2
    )

    # Oyuncu flagleri
    player_flags: list[FoulFlag] = []
    for pid, fouls in sorted(our_player_fouls.items()):
        has_yellow = yellow_states.get(pid, 0) > 0
        risk, msg = _player_risk(fouls, has_yellow)
        if risk != "safe":
            player_flags.append(FoulFlag(
                player_external_id=pid, fouls_committed=fouls,
                has_yellow=has_yellow, risk_level=risk, message=msg,
            ))

    ref_pressure = _referee_pressure(total_yellows_match)
    advice = _build_advice(
        opp_tactical=tactical_fouling,
        our_high=our_high_foul,
        escalation=escalation,
        ref_pressure=ref_pressure,
    )

    report = FoulPressureReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        window_min=window_min,
        our_fouls_total=our_fouls_total,
        our_fouls_window=our_fouls_window,
        opp_fouls_total=opp_fouls_total,
        opp_fouls_window=opp_fouls_window,
        our_foul_rate_per_10min=our_rate,
        opp_foul_rate_per_10min=opp_rate,
        tactical_fouling_alert=tactical_fouling,
        our_high_foul_alert=our_high_foul,
        escalation_alert=escalation,
        player_flags=tuple(player_flags),
        total_yellows_match=total_yellows_match,
        referee_card_pressure=ref_pressure,
        tactical_advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=team_external_id,
        metric="foul_pressure",
        value={
            "window_min": window_min,
            "our_fouls_window": our_fouls_window,
            "opp_fouls_window": opp_fouls_window,
            "our_foul_rate_per_10min": our_rate,
            "opp_foul_rate_per_10min": opp_rate,
            "tactical_fouling_alert": tactical_fouling,
            "our_high_foul_alert": our_high_foul,
            "escalation_alert": escalation,
            "referee_card_pressure": ref_pressure,
            "player_flags": [
                {"player_id": f.player_external_id, "fouls": f.fouls_committed,
                 "has_yellow": f.has_yellow, "risk_level": f.risk_level,
                 "message": f.message}
                for f in player_flags
            ],
            "tactical_advice": advice,
        },
        inputs={
            "current_minute": current_minute,
            "window_min": window_min,
            "total_yellows_match": total_yellows_match,
            "thresholds": {
                "tactical_fouling_per_10min": TACTICAL_FOULING_PER_10MIN,
                "our_high_foul_per_10min": OUR_HIGH_FOUL_PER_10MIN,
                "escalation_window_ratio": ESCALATION_WINDOW_RATIO,
                "high_ref_yellow": HIGH_REFEREE_CARD_THRESHOLD,
                "moderate_ref_yellow": MODERATE_REFEREE_CARD_THRESHOLD,
            },
        },
        formula=(
            "rate=(window_fouls/window)*10; "
            "opp_rate>=3→tactical_fouling; "
            "window_fouls/total>=0.6→escalation; "
            "total_yellows>=6→ref_high"
        ),
    )
    return EngineResult(value=report, audit=audit)
