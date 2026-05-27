"""Shot domain modeli — xG model girdisi.

Tek bir şutu temsil eder. Tracking veya event-feed adapter'lardan beslenecek;
şimdilik domain modeli + xG engine bağımsız test edilebilir.

Koordinat sistemi: saha 0-100 normalize (TrackingFrame ile aynı). x=100
hücum kalesi tarafı; (x=100, y=50) = hedefin tam ortası.

Body part: "head" | "right_foot" | "left_foot" | "other"
Pattern: "open_play" | "set_piece" | "penalty" | "fast_break" | "corner_kick"
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BodyPart = Literal["head", "right_foot", "left_foot", "other"]
ShotPattern = Literal[
    "open_play", "set_piece", "penalty", "fast_break", "corner_kick", "free_kick",
]


class Shot(BaseModel):
    """Tek bir şutun ham özellikleri.

    `x`, `y` saha-normalize 0-100; goal at (100, 50). Caller adapter
    sağlayıcının kendi koordinatından bu formata çevirir.
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    match_external_id: int
    player_external_id: int
    minute: float
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    body_part: BodyPart = "right_foot"
    pattern: ShotPattern = "open_play"
    is_goal: bool = False  # gerçek sonuç (training/calibration için)
