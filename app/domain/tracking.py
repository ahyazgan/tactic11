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
    """Bir oyuncunun bir anlık konumu.

    Kimlik alanları sağlayıcıya göre kısmi olabilir: StatsBomb 360 freeze
    frame'de yalnız event'in aktörü gerçek oyuncu id'siyle bilinir, diğerleri
    sentetik id + takım bilgisiyle gelir (`identity_estimated=True`).
    """

    model_config = ConfigDict(frozen=True)

    player_external_id: int
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    velocity_mps: float | None = None  # m/s, opsiyonel
    team_external_id: int | None = None
    is_actor: bool = False  # event'i yapan oyuncu (topla ilişkili)
    is_keeper: bool = False
    identity_estimated: bool = False


class TrackingFrame(BaseModel):
    """Bir maçın bir anına ait tüm oyuncu pozisyonları.

    Tipik veri: 25 Hz örnekleme (saniyede 25 frame). 90 dakikalık maç
    ≈ 135.000 frame. Bu yüzden ingest streaming + batch upsert gerektirir
    (Faz 6'da tracking adapter doldurur).

    Event-bağlantılı kaynaklarda (StatsBomb 360) her frame bir event'e
    çapalıdır: `event_uuid`/`event_type` dolu, `visible_area` kameranın
    gördüğü saha poligonu (0-100 normalize).
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    timestamp: datetime  # absolute UTC
    period: int  # 1, 2, (3=ET1, 4=ET2)
    minute: float  # maç başından dakika (0.0–120.0)
    ball: PlayerPosition | None = None  # top da bir "oyuncu" gibi pozisyona sahip
    ball_estimated: bool = False  # top görülmedi, komşu karelerden enterpole edildi
    players: tuple[PlayerPosition, ...]
    source: str | None = None
    event_uuid: str | None = None
    event_type: str | None = None
    possession_team_external_id: int | None = None
    visible_area: tuple[tuple[float, float], ...] | None = None
