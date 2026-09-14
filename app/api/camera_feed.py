"""Kamera canlı feed'i — takip hattından (tracking_frames) beslenen ReplayFeed.

## Neden bu sınıf var

WS canlı ekranı (`/matches/{id}/live`) yalnız StatsBomb replay'ini biliyordu:
saat replay saatiyle ilerler, veri önceden yüklenmiş event'lerden gelir.
Kulüp kamerası / RTSP / yayın kaynağında ise veri maç SÜRERKEN büyür
(`scripts.canli_mac` → `track_live` → `tracking_frames` + videodan türetilen
paslar `events`'e). Bu feed'de saat, replay değil, **işlenen son karedir**:
panel geriden geliyorsa ekran bunu söyler (gecikme = duvar saati − son karenin
yazılma anı). Gizlenmez; koç "63. dakikanın resmi, 3 dk geriden" diye görür.

Farklar:
- `window()` her çağrıda DB'den yeniden yüklenir (event'ler akarken değişir).
- `last_event_minute()` = son takip karesinin dakikası (canlı saat).
- `running_score()` videodan gol okunmaz → şut olaylarından; yoksa 0-0.
- `latency()` = şimdi − son karenin `created_at`'i (saniye); kare yoksa None.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.replay_feed import EventWindow
from app.data.loaders import load_match_events
from app.data.loaders.appearances import load_match_appearances
from app.db import models
from app.engine.live_lineup import PlayerAppearance
from app.engine.live_score import running_score_as_of
from app.sports import football

CAMERA_MODE = "camera_live"


@dataclass(frozen=True)
class CameraClock:
    latest_frame_minute: float | None
    latest_frame_at: datetime | None
    frames: int

    def latency_seconds(self, now: datetime | None = None) -> float | None:
        if self.latest_frame_at is None:
            return None
        ref = now or datetime.now(UTC)
        at = self.latest_frame_at
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return round(max(0.0, (ref - at).total_seconds()), 1)


class CameraLiveFeed:
    """Takip hattından canlı feed; veri maç sürerken DB'de büyür."""

    def __init__(self, session: Session, match_id: int) -> None:
        match = session.execute(
            select(models.Match).where(
                models.Match.sport == football.SPORT_NAME,
                models.Match.external_id == match_id,
            )
        ).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match {match_id} bulunamadı")
        self._session = session
        self.match_id = match_id
        self.home_team_id: int = match.home_team_external_id
        self.away_team_id: int = match.away_team_external_id
        self._appearances = load_match_appearances(session, match_id)
        self._loaded = load_match_events(session, match_id)

    # ---- canlı saat -------------------------------------------------------- #

    def clock(self) -> CameraClock:
        row = self._session.execute(
            select(
                func.max(models.TrackingFrameRow.minute),
                func.max(models.TrackingFrameRow.created_at),
                func.count(models.TrackingFrameRow.id),
            ).where(
                models.TrackingFrameRow.sport == football.SPORT_NAME,
                models.TrackingFrameRow.match_external_id == self.match_id,
            )
        ).one()
        minute, at, count = row
        return CameraClock(
            latest_frame_minute=None if minute is None else float(minute),
            latest_frame_at=at, frames=int(count or 0),
        )

    def refresh(self) -> None:
        """Event'leri yeniden yükle — videodan türetilen paslar akarken değişir."""
        self._session.expire_all()
        self._loaded = load_match_events(self._session, self.match_id)

    # ---- ReplayFeed protokolü --------------------------------------------- #

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
            self._loaded.shots, home_team_id=self.home_team_id,
            away_team_id=self.away_team_id, current_minute=current_minute,
        )

    def last_event_minute(self) -> float:
        return self.clock().latest_frame_minute or 0.0

    def mode(self) -> str:
        return CAMERA_MODE

    def appearances(self) -> list[PlayerAppearance] | None:
        return self._appearances or None
