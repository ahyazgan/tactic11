"""Lineup + per-player match stats domain modelleri (Prompt 4).

API-Football /fixtures/lineups + /fixtures/players endpoint'leri
mapping. Adapter ham JSON'u bu modellere çevirir; ingest
player_appearances tablosuna yazar.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LineupEntry(BaseModel):
    """Bir maçtaki bir oyuncunun ilk-11 / yedek + pozisyon kaydı."""

    model_config = ConfigDict(frozen=True)

    match_external_id: int
    team_external_id: int
    player_external_id: int
    player_name: str
    position_code: str | None = None  # GK | DR | DC | DL | MR | MC | ML | FR | FC | FL
    jersey: int | None = None
    is_starter: bool = True
    captain: bool = False
    formation_played: str | None = None  # ev/dep takım formasyonu, kayıt başına aynı


class PlayerMatchStats(BaseModel):
    """Bir oyuncunun bir maçtaki performans metrikleri."""

    model_config = ConfigDict(frozen=True)

    match_external_id: int
    team_external_id: int
    player_external_id: int
    minutes: int
    rating: float | None = None
    passes_total: int | None = None
    passes_accuracy: int | None = None  # 0-100 yüzde
    shots_total: int | None = None
    shots_on: int | None = None
    dribbles_attempts: int | None = None
    dribbles_success: int | None = None
    fouls_committed: int | None = None
    fouls_drawn: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    second_yellow: bool | None = None
    substituted_in_minute: int | None = None
    substituted_out_minute: int | None = None
    # Sezon istatistiği zenginleştirmesi — API-Football fixtures/players aynı
    # yanıtta verir; oyuncu özellik (1-20) türetimi bu alanlardan beslenir.
    goals: int | None = None
    assists: int | None = None
    goals_conceded: int | None = None     # kaleci: o maçta yenen gol
    saves: int | None = None              # kaleci kurtarışı
    key_passes: int | None = None
    tackles_total: int | None = None
    interceptions: int | None = None
    duels_total: int | None = None
    duels_won: int | None = None
