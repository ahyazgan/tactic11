"""API yanıt şemaları.

ORM satırlarını doğrudan sarmalamak için `from_attributes=True`. Surrogate
PK'lar dışarı sızdırılmaz; istemciler `external_id` üzerinden konuşur.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LeagueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sport: str
    external_id: int
    name: str
    season: int
    country: str | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sport: str
    external_id: int
    name: str
    country: str | None = None
    founded: int | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
