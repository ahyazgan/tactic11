"""Tracking ingest: adapter → DB (PR J1)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from app.data.ingest import (
    delete_match_frames,
    ingest_tracking_match,
)
from app.data.sources.tracking import TrackingDataSource
from app.db import models
from app.domain import PlayerPosition, TrackingFrame
from app.scheduler.registry import get


class _InMemorySource(TrackingDataSource):
    name = "memory"

    def __init__(self, frames: list[TrackingFrame]):
        self._frames = frames

    def get_match_frames(
        self, match_external_id: int, *, period: int | None = None,
    ) -> Iterable[TrackingFrame]:
        for f in self._frames:
            if period is not None and f.period != period:
                continue
            yield f


def _make_frame(match_id: int, t_offset_s: int, ball_x: float = 50.0) -> TrackingFrame:
    return TrackingFrame(
        sport="football",
        match_external_id=match_id,
        timestamp=datetime(2024, 8, 15, 18, 0, 0, tzinfo=UTC) + timedelta(seconds=t_offset_s),
        period=1,
        minute=t_offset_s / 60.0,
        ball=PlayerPosition(player_external_id=0, x=ball_x, y=50.0),
        players=(
            PlayerPosition(player_external_id=611001, x=10.0, y=50.0),
            PlayerPosition(player_external_id=607001, x=90.0, y=50.0),
        ),
    )


def test_ingest_writes_frames(session):
    src = _InMemorySource([_make_frame(7, 0), _make_frame(7, 2), _make_frame(7, 4)])
    report = ingest_tracking_match(session, src, match_external_id=7)
    session.commit()
    assert report.frames_written == 3
    assert report.frames_updated == 0
    rows = session.query(models.TrackingFrameRow).all()
    assert len(rows) == 3
    # players_json deserialize edilebilir + ball_x dolu
    parsed = json.loads(rows[0].players_json)
    assert {p["player_external_id"] for p in parsed} == {611001, 607001}
    assert rows[0].ball_x == 50.0


def test_ingest_is_idempotent_on_same_timestamp(session):
    src = _InMemorySource([_make_frame(7, 0, ball_x=30.0)])
    r1 = ingest_tracking_match(session, src, match_external_id=7)
    session.commit()
    assert r1.frames_written == 1

    # Aynı timestamp, farklı ball_x — update
    src2 = _InMemorySource([_make_frame(7, 0, ball_x=70.0)])
    r2 = ingest_tracking_match(session, src2, match_external_id=7)
    session.commit()
    assert r2.frames_written == 0
    assert r2.frames_updated == 1

    rows = session.query(models.TrackingFrameRow).all()
    assert len(rows) == 1
    assert rows[0].ball_x == 70.0  # update reflected


def test_delete_match_frames_clears(session):
    src = _InMemorySource([_make_frame(7, 0), _make_frame(7, 2)])
    ingest_tracking_match(session, src, match_external_id=7)
    session.commit()
    removed = delete_match_frames(session, sport="football", match_external_id=7)
    session.commit()
    assert removed == 2
    assert session.query(models.TrackingFrameRow).count() == 0


def test_ingest_handles_missing_ball(session):
    frame = TrackingFrame(
        sport="football", match_external_id=8,
        timestamp=datetime(2024, 8, 15, 18, 0, 0, tzinfo=UTC),
        period=1, minute=0.0,
        ball=None,
        players=(PlayerPosition(player_external_id=611001, x=50.0, y=50.0),),
    )
    ingest_tracking_match(session, _InMemorySource([frame]), match_external_id=8)
    session.commit()
    row = session.query(models.TrackingFrameRow).one()
    assert row.ball_x is None
    assert row.ball_y is None


def test_ingest_tracking_match_job_registered():
    spec = get("ingest_tracking_match")
    assert spec.name == "ingest_tracking_match"
    assert callable(spec.handler)


def test_ingest_with_fixture_tracking_source(session):
    """Tüm adapter+ingest stack: FixtureTrackingSource → DB."""
    from app.data.sources.fixture_tracking import FixtureTrackingSource

    src = FixtureTrackingSource()
    report = ingest_tracking_match(session, src, match_external_id=99)
    session.commit()
    assert report.frames_written == 30
    rows = session.query(models.TrackingFrameRow).filter_by(
        match_external_id=99
    ).all()
    assert len(rows) == 30
    # Generator topu 40→75 hareket ettiriyor; ortalama orta-üçte olmalı
    avg_x = sum(r.ball_x for r in rows if r.ball_x is not None) / len(rows)
    assert 50.0 < avg_x < 70.0
