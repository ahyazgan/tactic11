"""Event-level domain modelleri (Sprint 1 — StatsBomb event parse).

Mevcut `Shot` (app/domain/shot.py) shot event'leri taşıyor.
Bu modül diğer 3 event tipini ekliyor:

- PassEvent: pas eventleri (start_x/y + end_x/y, completed, key_pass, ...)
- DefensiveAction: defansif aksiyonlar (tackle, interception, ball_recovery, ...)
- Carry: top taşıma (start → end coordinatları)
- PossessionSequence: aynı possession_id'ye sahip eventler grubu (xT için)

Koordinat: 100×100 normalize (shot domain ile aynı). x=100 hücum kalesi.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PassType = Literal["regular", "long_ball", "through_ball", "cross", "switch", "lay_off", "corner", "free_kick", "throw_in", "goal_kick", "interception", "kick_off", "recovery"]
PassTechnique = Literal["regular", "inswinger", "outswinger", "straight", "through_ball"]
DefensiveActionType = Literal["tackle", "interception", "block", "ball_recovery", "clearance", "pressure", "duel_won"]


class PassEvent(BaseModel):
    """Bir pas eventi — xT/xA için ana girdi."""

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    player_external_id: int
    team_external_id: int
    minute: float
    period: int  # 1 = ilk yarı, 2 = ikinci yarı
    start_x: float = Field(ge=0.0, le=100.0)
    start_y: float = Field(ge=0.0, le=100.0)
    end_x: float = Field(ge=0.0, le=100.0)
    end_y: float = Field(ge=0.0, le=100.0)
    pass_type: PassType = "regular"
    technique: PassTechnique = "regular"
    completed: bool = True
    key_pass: bool = False  # şuta direkt ön asist
    assist: bool = False    # gole direkt asist
    possession_id: int | None = None  # StatsBomb possession sequence id


class DefensiveAction(BaseModel):
    """Defansif aksiyon — PPDA için ana girdi."""

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    player_external_id: int
    team_external_id: int
    minute: float
    period: int
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    action_type: DefensiveActionType
    successful: bool = True
    possession_id: int | None = None


class Carry(BaseModel):
    """Top taşıma — xT için (oyuncu topla ne kadar mesafe + threat aldı)."""

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    player_external_id: int
    team_external_id: int
    minute: float
    period: int
    start_x: float = Field(ge=0.0, le=100.0)
    start_y: float = Field(ge=0.0, le=100.0)
    end_x: float = Field(ge=0.0, le=100.0)
    end_y: float = Field(ge=0.0, le=100.0)
    possession_id: int | None = None


class PossessionSequence(BaseModel):
    """Aynı possession_id'deki tüm eventler — build_up_pattern için."""

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    possession_id: int
    team_external_id: int  # possession'ı yapan takım
    passes: tuple[PassEvent, ...] = ()
    carries: tuple[Carry, ...] = ()
    ended_with_shot: bool = False
    ended_with_goal: bool = False
    start_zone: str | None = None  # "defensive_third" | "middle_third" | "attacking_third"
