"""Tracking domain modelleri.

Bir takımın tracking sağlayıcısından gelen sahada-pozisyon zaman serisi için
şekil. Faz 6'da gerçek adapter doldurur; engine bu modelleri tüketir
(saf hesap — DB/HTTP bilmez).

Koordinat sistemi: saha 0-100 normalize (sağlayıcıdan bağımsız). x=0
ev sahibi defans bölgesi, x=100 hücum bölgesi varsayılır; sağlayıcı eşlemesi
adapter'da yapılır.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlayerPosition(BaseModel):
    """Bir oyuncunun bir anlık konumu."""

    model_config = ConfigDict(frozen=True)

    player_external_id: int
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    velocity_mps: float | None = None  # m/s, opsiyonel


class TrackingFrame(BaseModel):
    """Bir maçın bir anına ait tüm oyuncu pozisyonları.

    Tipik veri: 25 Hz örnekleme (saniyede 25 frame). 90 dakikalık maç
    ≈ 135.000 frame. Bu yüzden ingest streaming + batch upsert gerektirir
    (Faz 6'da tracking adapter doldurur).
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    timestamp: datetime  # absolute UTC
    period: int  # 1, 2, (3=ET1, 4=ET2)
    minute: float  # maç başından dakika (0.0–120.0)
    ball: PlayerPosition | None = None  # top da bir "oyuncu" gibi pozisyona sahip
    players: tuple[PlayerPosition, ...]
