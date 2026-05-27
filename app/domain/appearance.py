"""Player appearance — bir oyuncunun bir maçtaki dakikası.

Domain seviyesinde minimum şekil; DB/ingest henüz doldurmuyor (lineup adapter
Faz 6 veya Faz 2.5'te eklenecek). Engine bugün bu şekli direkt tüketebilsin
diye burada tutuluyor.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlayerAppearance(BaseModel):
    model_config = ConfigDict(frozen=True)

    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime
