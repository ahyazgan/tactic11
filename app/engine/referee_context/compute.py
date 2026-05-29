"""Referee Context — hakem / disiplin bağlamı (Faz 7 J: #11, #12).

İki sinyal (payload-reçete):
11. Hakem eğilimi: hakemin maç başı düdük/kart ortalaması yüksekse fiziksel
    oyun kart riski yüksek → uyarı.
12. Avantaj penceresi: rakibin kart sınırındaki oyuncusu → o oyuncunun
    bölgesine yüklen, ikinci sarı baskısı yarat.

Pure: hakem istatistikleri + rakip kart-sınırı oyuncu listesi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.referee_context"
ENGINE_VERSION = "1"

# Hakem eğilim eşikleri (lig ortalamasına göre kalibre edilebilir)
STRICT_CARDS_PER_GAME = 4.5
STRICT_FOULS_PER_GAME = 26.0


@dataclass(frozen=True)
class AdvantageTarget:
    player_external_id: int
    position_zone: str
    note: str


@dataclass(frozen=True)
class RefereeContextReport:
    team_external_id: int
    current_minute: float
    # #11 hakem eğilimi
    strict_referee: bool
    cards_per_game: float
    fouls_per_game: float
    card_risk_note: str
    # #12 avantaj penceresi
    advantage_targets: tuple[AdvantageTarget, ...] = field(default_factory=tuple)
    alerts: tuple[str, ...] = field(default_factory=tuple)


def compute_referee_context(
    team_external_id: int,
    *,
    current_minute: float,
    cards_per_game: float = 0.0,
    fouls_per_game: float = 0.0,
    opponent_card_edge_players: list[dict[str, Any]] | None = None,
) -> EngineResult[RefereeContextReport]:
    # #11 hakem eğilimi
    strict = (cards_per_game >= STRICT_CARDS_PER_GAME
              or fouls_per_game >= STRICT_FOULS_PER_GAME)
    if strict:
        card_note = (
            "Sıkı hakem — fiziksel oyunda kart riski yüksek, sert müdahaleden kaçın"
        )
    else:
        card_note = "Hakem normal eğilimde — standart fiziksel oyun makul"

    # #12 avantaj penceresi — rakip kart-sınırı oyuncular
    targets: list[AdvantageTarget] = []
    for pl in (opponent_card_edge_players or []):
        pid = int(pl.get("player_id", 0))
        zone = str(pl.get("position_zone", pl.get("zone", "bilinmiyor")))
        note = (f"rakip #{pid} sarı kart sınırında — {zone} bölgesine yüklen, "
                "ikinci sarı baskısı yarat")
        targets.append(AdvantageTarget(pid, zone, note))

    alerts: list[str] = []
    if strict:
        alerts.append(f"HAKEM: {card_note} (kart/maç {cards_per_game:.1f})")
    for t in targets:
        alerts.append(f"AVANTAJ: {t.note}")

    report = RefereeContextReport(
        team_external_id=team_external_id,
        current_minute=current_minute,
        strict_referee=strict,
        cards_per_game=round(cards_per_game, 2),
        fouls_per_game=round(fouls_per_game, 2),
        card_risk_note=card_note,
        advantage_targets=tuple(targets),
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="referee_context",
        value={
            "strict_referee": strict,
            "advantage_targets": [t.player_external_id for t in targets],
            "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute,
            "cards_per_game": cards_per_game, "fouls_per_game": fouls_per_game,
        },
        formula="kart/faul maç ortalaması eşiği → sıkı hakem; rakip kart-sınırı → avantaj zonu",
    )
    return EngineResult(value=report, audit=audit)
