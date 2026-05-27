"""Match domain modeli."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Match(BaseModel):
    """Bir maçı temsil eder.

    Takım/lig referansları surrogate ID değil `external_id` üzerinden taşınır;
    DB katmanı eşlemeyi sport+external_id üzerinden yapar. `kickoff` UTC, naive
    olmamalı. `status` API-Football "status short" kodu (NS, FT, AET, ...).
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    external_id: int
    league_external_id: int
    season: int
    kickoff: datetime
    status: str
    home_team_external_id: int
    away_team_external_id: int
    home_score: int | None = None
    away_score: int | None = None
