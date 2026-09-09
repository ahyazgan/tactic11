"""Video takibi JSON kaynağı — `scripts/track_video.py` çıktısını ingest'e verir.

CV işçisi (venv-cv, torch) kareleri JSON'a yazar; ana uygulama bu kaynakla
`ingest_tracking_match` üzerinden tracking_frames'e alır. Böylece torch ana
ortama girmez, işçi başka makinede/GPU'da da koşabilir.

JSON şeması: app.tracking.frames.frames_to_json çıktısı
  {"match_external_id": 990001, "source": "video_tracking", "frames": [TrackingFrame...]}
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from app.core.logging import get_logger
from app.data.sources.tracking import TrackingDataSource
from app.domain import TrackingFrame
from app.tracking.frames import frames_from_json

log = get_logger(__name__)


class VideoJsonTrackingSource(TrackingDataSource):
    """Tek bir JSON dosyasından TrackingFrame stream'i."""

    name = "video_tracking"

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def get_match_frames(
        self,
        match_external_id: int,
        *,
        period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        with open(self._path, encoding="utf-8") as f:
            payload = json.load(f)
        file_match = payload.get("match_external_id")
        if file_match is not None and int(file_match) != match_external_id:
            log.info(
                "video_tracking: JSON match=%s → %d olarak ingest ediliyor",
                file_match, match_external_id,
            )
        frames = frames_from_json(payload, match_id=match_external_id)
        for fr in frames:
            if period is not None and fr.period != period:
                continue
            yield fr
        log.info("video_tracking: %s → %d frame", self._path.name, len(frames))
