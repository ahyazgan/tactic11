"""StatsBomb 360 tracking adapter iskeleti (Faz 5 #45).

StatsBomb Open Data 360 endpoint event-bağlantılı "freeze frame" verisi
sağlar — sürekli tracking değil, her event anında bir snapshot.

Endpoint pattern:
    https://raw.githubusercontent.com/statsbomb/open-data/master/data/three-sixty/{match_id}.json

Şema (per event):
    [
      {
        "event_uuid": "...",
        "visible_area": [...],
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

Sınırlamalar (iskelet):
- freeze_frame entry'lerde player_external_id YOK — `teammate` bool var.
  player_external_id=0 atanır; gerçek eşleştirme caller'da match_lineup ile
  cross-reference ile yapılmalı.
- timestamp absolute değil — events.json gerektirir; burada `now()` proxy.
  Gerçek pipeline events ingest ile birleştirmeli.
- minute=0.0 placeholder — yine event paralel ingest'i gerektirir.

İskelet amacı: ABC sözleşmesini somutlaştırmak + StatsBomb endpoint
şemasını tipler. Pilot kulüp 360 erişimi yokken bile arayüz canlı kalır;
endpoint URL veya yerel JSON path swap edilebilir.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
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

# Synthetic team_id offsets — placeholder ID'ler. Gerçek eşleme
# match_lineup tablosu ile dış katmanda yapılır (TODO).
HOME_PLAYER_BASE_ID = 10000
AWAY_PLAYER_BASE_ID = 20000


class StatsBomb360Error(RuntimeError):
    """360 endpoint'i, ağ veya parse hatası."""


class StatsBomb360Adapter(TrackingDataSource):
    """Event-bağlantılı freeze frame → TrackingFrame stream."""

    name = "statsbomb_360"

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_API_BASE,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._client = http_client  # test'te mock client geçilir
        self._timeout = timeout_seconds

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
    def _convert_entry(
        entry: dict[str, Any],
        index: int,
    ) -> PlayerPosition | None:
        """freeze_frame entry → PlayerPosition (id sentetik)."""
        loc = entry.get("location")
        if not loc:
            return None
        x, y = StatsBomb360Adapter._normalize_xy(loc)
        # ID: teammate=True → home base offset; False → away base offset
        # index sırasıyla artar; aynı entry tekrar ederse aynı ID döner
        is_teammate = bool(entry.get("teammate"))
        base = HOME_PLAYER_BASE_ID if is_teammate else AWAY_PLAYER_BASE_ID
        return PlayerPosition(player_external_id=base + index, x=x, y=y)

    def _build_frame(
        self,
        match_external_id: int,
        event: dict[str, Any],
        timestamp: datetime,
    ) -> TrackingFrame | None:
        """Bir event → TrackingFrame. freeze_frame yoksa None döndür."""
        freeze = event.get("freeze_frame")
        if not isinstance(freeze, list) or not freeze:
            return None
        players: list[PlayerPosition] = []
        for i, entry in enumerate(freeze):
            if not isinstance(entry, dict):
                continue
            pos = self._convert_entry(entry, i)
            if pos is not None:
                players.append(pos)
        if not players:
            return None
        return TrackingFrame(
            sport=football.SPORT_NAME,
            match_external_id=match_external_id,
            timestamp=timestamp,
            period=1,  # placeholder — events.json'dan gelmeli
            minute=0.0,  # placeholder — events.json'dan gelmeli
            ball=None,
            players=tuple(players),
        )

    def get_match_frames(
        self,
        match_external_id: int,
        *,
        period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        """Bir maçın tüm freeze frame'leri → TrackingFrame stream.

        `period` filtresi şu an no-op (placeholder period=1 kullanıldığı için);
        events.json eşlemesi eklendiğinde aktif olacak.
        """
        events = self._fetch_360_data(match_external_id)
        now = datetime.now(UTC)
        produced = 0
        for ev in events:
            if not isinstance(ev, dict):
                continue
            frame = self._build_frame(match_external_id, ev, now)
            if frame is None:
                continue
            if period is not None and frame.period != period:
                continue
            yield frame
            produced += 1
        log.info(
            "statsbomb_360 match=%d produced %d frames (event-anchored)",
            match_external_id, produced,
        )
