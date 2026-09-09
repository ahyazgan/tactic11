"""StatsBomb 360 tracking adapter.

StatsBomb Open Data 360 endpoint event-bağlantılı "freeze frame" verisi
sağlar — sürekli tracking değil, her event anında bir snapshot.

Endpoint pattern:
    https://raw.githubusercontent.com/statsbomb/open-data/master/data/three-sixty/{match_id}.json

Şema (per event):
    [
      {
        "event_uuid": "...",
        "visible_area": [x0, y0, x1, y1, ...],   # düz liste, çiftler halinde
        "freeze_frame": [
          {"teammate": true,  "actor": true,  "keeper": false,
           "location": [88.4, 47.3]},
          ...
        ]
      },
      ...
    ]

StatsBomb saha koordinatları **120 × 80** yard; bizim domain
**0-100 × 0-100** normalized. Burada doğrusal olarak normalize edilir.

Kimlik / zaman bilgisi 360 dosyasında YOK; `events/{match_id}.json` ile
`event_uuid` üzerinden birleşir. Adapter'a `events` (ham event listesi)
verilirse:
- period/minute/second gerçek event'ten,
- aktör oyuncu gerçek player id'siyle, takım id'leri `teammate` + event
  takımı (+ home/away) üzerinden,
- top pozisyonu event location'ından
doldurulur. Verilmezse eski iskelet davranışı (sentetik id, minute=0) korunur.

Aktör dışındaki oyuncular 360'ta isimsizdir → sentetik id + `identity_estimated`.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.logging import get_logger
from app.data.sources.tracking import TrackingDataSource
from app.domain import PlayerPosition, TrackingFrame
from app.sports import football

log = get_logger(__name__)

DEFAULT_API_BASE = (
    "https://raw.githubusercontent.com/"
    "statsbomb/open-data/master/data/three-sixty"
)

# StatsBomb pitch — 120 × 80 yard. Normalize to 0-100 × 0-100.
SB_PITCH_X = 120.0
SB_PITCH_Y = 80.0

# Synthetic player id offsets — aktör dışındaki oyuncular 360'ta isimsiz.
HOME_PLAYER_BASE_ID = 10000
AWAY_PLAYER_BASE_ID = 20000

# Event-anchored frame'lerin sentetik zaman ekseni. Gerçek kickoff bilinmiyor;
# (match, timestamp) tekilliği için maç saati + event sırası (µs) kullanılır.
FRAME_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


class StatsBomb360Error(RuntimeError):
    """360 endpoint'i, ağ veya parse hatası."""


@dataclass(frozen=True)
class EventMeta:
    """events.json'dan bir event'in frame için gereken özeti."""

    period: int
    minute: float
    type_name: str | None
    team_id: int | None
    player_id: int | None
    possession_team_id: int | None
    location: tuple[float, float] | None


def index_events(events: Iterable[dict[str, Any]]) -> dict[str, EventMeta]:
    """Ham StatsBomb event listesi → uuid → EventMeta."""
    out: dict[str, EventMeta] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        uuid = ev.get("id")
        if not uuid:
            continue
        loc = ev.get("location")
        location: tuple[float, float] | None = (
            (loc[0], loc[1]) if isinstance(loc, list) and len(loc) >= 2 else None
        )
        out[str(uuid)] = EventMeta(
            period=int(ev.get("period", 1) or 1),
            minute=float(ev.get("minute", 0) or 0) + float(ev.get("second", 0) or 0) / 60.0,
            type_name=(ev.get("type") or {}).get("name"),
            team_id=(ev.get("team") or {}).get("id"),
            player_id=(ev.get("player") or {}).get("id"),
            possession_team_id=(ev.get("possession_team") or {}).get("id"),
            location=location,
        )
    return out


class StatsBomb360Adapter(TrackingDataSource):
    """Event-bağlantılı freeze frame → TrackingFrame stream."""

    name = "statsbomb_360"

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_API_BASE,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        events: Iterable[dict[str, Any]] | None = None,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._client = http_client  # test'te mock client geçilir
        self._timeout = timeout_seconds
        self._events = index_events(events) if events is not None else None
        self._home_team_id = home_team_id
        self._away_team_id = away_team_id

    def _fetch_360_data(self, match_external_id: int) -> list[dict[str, Any]]:
        """Bir maçın 360 JSON'unu çek + parse. Network hata → StatsBomb360Error."""
        url = f"{self._api_base}/{match_external_id}.json"
        try:
            if self._client is not None:
                r = self._client.get(url, timeout=self._timeout)
            else:
                r = httpx.get(url, timeout=self._timeout)
        except httpx.HTTPError as e:
            raise StatsBomb360Error(f"HTTP error: {e}") from e
        if r.status_code == 404:
            raise StatsBomb360Error(
                f"match {match_external_id} için 360 verisi yok (404)",
            )
        if r.status_code >= 400:
            raise StatsBomb360Error(
                f"HTTP {r.status_code}: {r.text[:200]}",
            )
        try:
            payload = r.json()
        except ValueError as e:
            raise StatsBomb360Error(f"JSON parse: {e}") from e
        if not isinstance(payload, list):
            raise StatsBomb360Error(
                f"beklenen list, gelen {type(payload).__name__}",
            )
        return payload

    @staticmethod
    def _normalize_xy(loc: list[float] | tuple[float, ...]) -> tuple[float, float]:
        """SB 120×80 → 0-100×0-100. Aralık dışı koordinatlar clamp'lenir."""
        if not loc or len(loc) < 2:
            return 50.0, 50.0
        x = max(0.0, min(SB_PITCH_X, float(loc[0])))
        y = max(0.0, min(SB_PITCH_Y, float(loc[1])))
        return round(x / SB_PITCH_X * 100, 3), round(y / SB_PITCH_Y * 100, 3)

    @staticmethod
    def _normalize_area(area: Any) -> tuple[tuple[float, float], ...] | None:
        """visible_area düz [x0,y0,x1,y1,...] → normalize nokta çiftleri."""
        if not isinstance(area, list) or len(area) < 6:
            return None
        pts: list[tuple[float, float]] = []
        for i in range(0, len(area) - 1, 2):
            pts.append(StatsBomb360Adapter._normalize_xy([area[i], area[i + 1]]))
        return tuple(pts)

    @staticmethod
    def _convert_entry(
        entry: dict[str, Any],
        index: int,
        *,
        meta: EventMeta | None = None,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> PlayerPosition | None:
        """freeze_frame entry → PlayerPosition.

        Aktör (event'i yapan) gerçek player id alır; diğerleri sentetik
        (base + index) ve `identity_estimated=True`.
        """
        loc = entry.get("location")
        if not loc:
            return None
        x, y = StatsBomb360Adapter._normalize_xy(loc)
        is_teammate = bool(entry.get("teammate"))
        is_actor = bool(entry.get("actor"))
        is_keeper = bool(entry.get("keeper"))

        team_id: int | None = None
        if meta is not None and meta.team_id is not None:
            if is_teammate:
                team_id = meta.team_id
            elif home_team_id is not None and away_team_id is not None:
                team_id = away_team_id if meta.team_id == home_team_id else home_team_id

        if is_actor and meta is not None and meta.player_id is not None:
            return PlayerPosition(
                player_external_id=meta.player_id, x=x, y=y,
                team_external_id=team_id, is_actor=True, is_keeper=is_keeper,
                identity_estimated=False,
            )

        base = HOME_PLAYER_BASE_ID if is_teammate else AWAY_PLAYER_BASE_ID
        return PlayerPosition(
            player_external_id=base + index, x=x, y=y,
            team_external_id=team_id, is_actor=is_actor, is_keeper=is_keeper,
            identity_estimated=True,
        )

    def _build_frame(
        self,
        match_external_id: int,
        event: dict[str, Any],
        timestamp: datetime,
        *,
        order: int = 0,
    ) -> TrackingFrame | None:
        """Bir event → TrackingFrame. freeze_frame yoksa None döndür."""
        freeze = event.get("freeze_frame")
        if not isinstance(freeze, list) or not freeze:
            return None
        uuid = event.get("event_uuid")
        meta = self._events.get(str(uuid)) if (self._events and uuid) else None

        players: list[PlayerPosition] = []
        for i, entry in enumerate(freeze):
            if not isinstance(entry, dict):
                continue
            pos = self._convert_entry(
                entry, i, meta=meta,
                home_team_id=self._home_team_id, away_team_id=self._away_team_id,
            )
            if pos is not None:
                players.append(pos)
        if not players:
            return None

        period = 1
        minute = 0.0
        ball: PlayerPosition | None = None
        if meta is not None:
            period = meta.period
            minute = meta.minute
            timestamp = FRAME_EPOCH + timedelta(seconds=minute * 60.0, microseconds=order)
            if meta.location is not None:
                bx, by = self._normalize_xy(meta.location)
                ball = PlayerPosition(player_external_id=0, x=bx, y=by)

        return TrackingFrame(
            sport=football.SPORT_NAME,
            match_external_id=match_external_id,
            timestamp=timestamp,
            period=period,
            minute=minute,
            ball=ball,
            players=tuple(players),
            source=self.name,
            event_uuid=str(uuid) if uuid else None,
            event_type=meta.type_name if meta else None,
            possession_team_external_id=meta.possession_team_id if meta else None,
            visible_area=self._normalize_area(event.get("visible_area")),
        )

    def get_match_frames(
        self,
        match_external_id: int,
        *,
        period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        """Bir maçın tüm freeze frame'leri → TrackingFrame stream (dakika sıralı)."""
        events = self._fetch_360_data(match_external_id)
        now = datetime.now(UTC)
        frames: list[TrackingFrame] = []
        for order, ev in enumerate(events):
            if not isinstance(ev, dict):
                continue
            frame = self._build_frame(match_external_id, ev, now, order=order)
            if frame is None:
                continue
            if period is not None and frame.period != period:
                continue
            frames.append(frame)
        # 360 dosyası event sırasında gelir ama garanti değil; event meta varsa
        # dakikaya göre sırala (timestamp order µs'yi taşıdığı için kararlı).
        if self._events:
            frames.sort(key=lambda f: f.timestamp)
        log.info(
            "statsbomb_360 match=%d produced %d frames (event-anchored, meta=%s)",
            match_external_id, len(frames), self._events is not None,
        )
        yield from frames
