"""Engine giriş tipleri için structural Protocol'ler.

Engine fonksiyonları hem `domain/match.py` pydantic modelini hem
`db/models.py` SQLAlchemy modelini kabul etsin — ikisi aynı alanları
taşıyor, ikisi de saf. Bu Protocol her ikisini de structurally karşılar
(mypy `runtime_checkable` aramaz; isinstance check yapmıyoruz).

Engine kuralı bozulmuyor — Protocol da bir "girdi şekli", DB/HTTP'ye
bağımlılık değil.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class MatchLike(Protocol):
    """Engine'in tükettiği maç şekli (domain ve DB modelleri uyumlu)."""

    sport: str
    external_id: int
    league_external_id: int
    season: int
    kickoff: datetime
    status: str
    home_team_external_id: int
    away_team_external_id: int
    home_score: int | None
    away_score: int | None


class PlayerAppearanceLike(Protocol):
    """Engine.load'un tükettiği oyuncu-dakika şekli (domain ve DB uyumlu)."""

    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime
