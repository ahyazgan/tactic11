"""Player domain modeli."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class Player(BaseModel):
    """Bir oyuncuyu temsil eder.

    `position` futbol için `sports/football.py`'deki POSITIONS'tan biri olmalı;
    doğrulama validation katmanında yapılır, model burada serbesttir ki başka
    sporlar da aynı yapıyı kullanabilsin.
    """

    model_config = ConfigDict(frozen=True)

    sport: str
    external_id: int
    name: str
    position: str | None = None
    birth_date: date | None = None
    nationality: str | None = None
