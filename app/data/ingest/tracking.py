"""Tracking frame ingest — adapter'dan stream alıp DB'ye yazar.

Sözleşme:
    source: TrackingDataSource (örn. FixtureTrackingSource, ya da ileride
            SecondSpectrumAdapter)
    output: TrackingIngestReport (kaç frame yazıldı, idempotent davranış)

Idempotent: (sport, match_external_id, timestamp) tekil; tekrar çalıştırılırsa
mevcut satırlar güncellenir. "Tüm maçı baştan al" için caller önce
`delete_match_frames(...)` çağırır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.data.sources.tracking import TrackingDataSource
from app.db import models
from app.domain import TrackingFrame

log = get_logger(__name__)


@dataclass(frozen=True)
class TrackingIngestReport:
    match_external_id: int
    frames_written: int
    frames_updated: int


def _serialize_players(frame: TrackingFrame) -> str:
    return json.dumps(
        [
            {
                "player_external_id": p.player_external_id,
                "x": p.x,
                "y": p.y,
                "velocity_mps": p.velocity_mps,
            }
            for p in frame.players
        ],
        ensure_ascii=False,
    )


def delete_match_frames(session: Session, *, sport: str, match_external_id: int) -> int:
    """Bir maçın tüm frame'lerini sil; yeniden ingest için."""
    result = session.execute(
        delete(models.TrackingFrameRow).where(
            models.TrackingFrameRow.sport == sport,
            models.TrackingFrameRow.match_external_id == match_external_id,
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def ingest_tracking_match(
    session: Session,
    source: TrackingDataSource,
    *,
    match_external_id: int,
    sport: str = "football",
) -> TrackingIngestReport:
    """Bir maç için adapter'dan tüm frame'leri okuyup DB'ye yaz.

    Mevcut (timestamp eşleşen) satırlar update; yeniler insert.
    """
    now = datetime.now(UTC)
    written = 0
    updated = 0

    def _normalize(ts: datetime) -> datetime:
        # SQLite tz-strip + Postgres timezone=True'yu birleştir: tek
        # canonical form (UTC, naive) lookup için.
        if ts.tzinfo is not None:
            ts = ts.astimezone(UTC).replace(tzinfo=None)
        return ts

    existing_rows = session.execute(
        select(models.TrackingFrameRow.id, models.TrackingFrameRow.timestamp).where(
            models.TrackingFrameRow.sport == sport,
            models.TrackingFrameRow.match_external_id == match_external_id,
        )
    ).all()
    existing_by_ts = {_normalize(ts): row_id for row_id, ts in existing_rows}

    for frame in source.get_match_frames(match_external_id):
        ts = frame.timestamp
        ts_key = _normalize(ts)
        players_blob = _serialize_players(frame)
        ball_x = frame.ball.x if frame.ball else None
        ball_y = frame.ball.y if frame.ball else None
        if ts_key in existing_by_ts:
            row = session.get(models.TrackingFrameRow, existing_by_ts[ts_key])
            assert row is not None
            row.period = frame.period
            row.minute = frame.minute
            row.ball_x = ball_x
            row.ball_y = ball_y
            row.players_json = players_blob
            updated += 1
        else:
            session.add(models.TrackingFrameRow(
                sport=sport,
                match_external_id=match_external_id,
                timestamp=ts,
                period=frame.period,
                minute=frame.minute,
                ball_x=ball_x,
                ball_y=ball_y,
                players_json=players_blob,
                created_at=now,
            ))
            written += 1

    session.flush()
    log.info(
        "tracking ingest: match=%d written=%d updated=%d",
        match_external_id, written, updated,
    )
    return TrackingIngestReport(
        match_external_id=match_external_id,
        frames_written=written,
        frames_updated=updated,
    )
