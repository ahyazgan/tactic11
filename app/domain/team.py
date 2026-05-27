"""Team domain modeli."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Team(BaseModel):
    """Bir takımı temsil eder (lig/sezondan bağımsız kimlik)."""

    model_config = ConfigDict(frozen=True)

    sport: str
    external_id: int
    name: str
    country: str | None = None
    founded: int | None = None
