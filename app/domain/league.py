"""League domain modeli."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class League(BaseModel):
    """Bir spor ligini temsil eder (sezon ile birlikte tekil).

    `external_id` veri kaynağındaki ID (örn. API-Football league.id). `sport`
    `sports/<spor>.py`'deki `SPORT_NAME` ile aynı string olmalı.
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    external_id: int
    name: str
    season: int
    country: str | None = None
