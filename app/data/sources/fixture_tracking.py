"""Lokal JSON tabanlı tracking adapter — production öncesi demo + test.

`TrackingDataSource` ABC'nin somut implementasyonu. `tests/fixtures/`
altındaki `tracking_<match_id>.json`'dan okur ve `TrackingFrame` listesi
döner. Gerçek bir vendor (SecondSpectrum, Hawk-Eye) bağlanana kadar:

- engine.tracking testlerinde frame'leri inline üretmek yerine
  reproducible fixture'tan beslemek
- scripts/demo.py'ın "ball-zone distribution" bölümünü çalıştırabilmek
- ingest sözleşmesini somutlaştırmak (vendor swap'ı kolay)

için kullanılır. Vendor geldiğinde bu sınıfın yanına `SecondSpectrumAdapter`
(veya benzeri) eklenir; üst katman (engine, scheduler) değişmez.

JSON şeması (örnek `tracking_99.json`):
{
  "match_external_id": 99,
  "sport": "football",
  "frames": [
    {
      "timestamp": "2024-08-15T18:00:00+00:00",
      "period": 1,
      "minute": 0.0,
      "ball": {"player_external_id": 0, "x": 50.0, "y": 50.0},
      "players": [
        {"player_external_id": 6111, "x": 10.0, "y": 50.0},
        ...
      ]
    },
    ...
  ]
}
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.data.sources.tracking import TrackingDataSource
from app.domain import PlayerPosition, TrackingFrame
from app.sports import football

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"


class TrackingFixtureMissing(FileNotFoundError):
    """İstenen match için tracking fixture dosyası yok."""


class FixtureTrackingSource(TrackingDataSource):
    """tests/fixtures/tracking_<match_id>.json'dan TrackingFrame stream'i."""

    name = "fixture_tracking"

    def __init__(self, fixture_dir: Path | str | None = None) -> None:
        self._dir = Path(fixture_dir) if fixture_dir else DEFAULT_FIXTURE_DIR

    def fixture_path(self, match_external_id: int) -> Path:
        return self._dir / f"tracking_{match_external_id}.json"

    def has_fixture(self, match_external_id: int) -> bool:
        return self.fixture_path(match_external_id).exists()

    def get_match_frames(
        self,
        match_external_id: int,
        *,
        period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        fp = self.fixture_path(match_external_id)
        if not fp.exists():
            raise TrackingFixtureMissing(
                f"tracking fixture yok: {fp.name} "
                f"(scripts/generate_tracking_fixture.py ile üret)"
            )
        log.info("fixture_tracking okuma: %s", fp.name)
        with fp.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        sport = str(payload.get("sport", football.SPORT_NAME))
        frames = payload.get("frames") or []
        for raw in frames:
            if period is not None and int(raw.get("period", 1)) != period:
                continue
            yield _to_frame(sport, match_external_id, raw)


def _to_position(raw: dict[str, Any]) -> PlayerPosition:
    return PlayerPosition(
        player_external_id=int(raw["player_external_id"]),
        x=float(raw["x"]),
        y=float(raw["y"]),
        velocity_mps=(
            float(raw["velocity_mps"]) if raw.get("velocity_mps") is not None else None
        ),
    )


def _to_frame(sport: str, match_external_id: int, raw: dict[str, Any]) -> TrackingFrame:
    ts_raw = raw["timestamp"]
    ts = (
        datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if isinstance(ts_raw, str)
        else ts_raw
    )
    ball_raw = raw.get("ball")
    players = tuple(_to_position(p) for p in raw.get("players", []))
    return TrackingFrame(
        sport=sport,
        match_external_id=match_external_id,
        timestamp=ts,
        period=int(raw.get("period", 1)),
        minute=float(raw.get("minute", 0.0)),
        ball=_to_position(ball_raw) if ball_raw else None,
        players=players,
    )
