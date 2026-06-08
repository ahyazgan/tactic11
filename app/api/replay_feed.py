"""ReplayFeed — canlı snapshot'ın veri kaynağı soyutlaması.

Bugün tek somut uygulama `StatsBombReplayFeed`: maçın event'lerini DB'den
**bir kez** yükler (her-tick reload yerine) ve dakikaya göre dilimler. Skoru
final-skordan değil, o dakikaya kadarki gollerden türetir (app.engine.live_score).

Gelecekte gerçek bir canlı feed (Opta/StatsBomb Pro) aynı `ReplayFeed`
Protocol'ünü implement edip snapshot builder'a veya engine'lere dokunmadan
girer — `window` "şu ana kadar gelen event'ler", `running_score`/`last_event_minute`
provider'dan gelir. Bu yüzden bu sınıf api katmanında (DB/loader dokunabilir);
engine saf kalır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.loaders import load_match_events
from app.db import models
from app.engine.live_score import running_score_as_of
from app.sports import football


@dataclass(frozen=True)
class EventWindow:
    """`current_minute`'a kadar olan event'ler (engine-hazır)."""

    passes: list
    carries: list
    defensive_actions: list
    shots: list


class ReplayFeed(Protocol):
    """Canlı snapshot'ın ihtiyaç duyduğu minimal veri arayüzü."""

    home_team_id: int
    away_team_id: int

    def window(self, current_minute: float) -> EventWindow: ...
    def running_score(self, current_minute: float) -> tuple[int, int]: ...
    def last_event_minute(self) -> float: ...
    def mode(self) -> str: ...


class StatsBombReplayFeed:
    """StatsBomb open event'lerini bir kez yükleyip dakikaya göre dilimler."""

    def __init__(self, session: Session, match_id: int) -> None:
        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")
        self.match_id = match_id
        self.home_team_id: int = match.home_team_external_id
        self.away_team_id: int = match.away_team_external_id
        self._loaded = load_match_events(session, match_id)
        all_minutes = [
            e.minute
            for group in (
                self._loaded.passes,
                self._loaded.carries,
                self._loaded.defensive_actions,
                self._loaded.shots,
            )
            for e in group
        ]
        self._last_event_minute = max(all_minutes, default=0.0)

    def window(self, current_minute: float) -> EventWindow:
        return EventWindow(
            passes=[p for p in self._loaded.passes if p.minute <= current_minute],
            carries=[c for c in self._loaded.carries if c.minute <= current_minute],
            defensive_actions=[
                d for d in self._loaded.defensive_actions if d.minute <= current_minute
            ],
            shots=[s for s in self._loaded.shots if s.minute <= current_minute],
        )

    def running_score(self, current_minute: float) -> tuple[int, int]:
        return running_score_as_of(
            self._loaded.shots,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            current_minute=current_minute,
        )

    def last_event_minute(self) -> float:
        return self._last_event_minute

    def mode(self) -> str:
        return "replay_statsbomb"
