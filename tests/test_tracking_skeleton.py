"""Tracking iskeleti + v1'de implement edilen ball_zone_distribution.

`compute_pressure` ve `compute_formation` Faz 6'da gerçek tracking ingest
geldiğinde doldurulacak; bugün stub kalır. `compute_ball_zone_distribution`
v1'de implement edildi — frame'lerden bağımsız bir frame-level metric.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.data.sources.tracking import TrackingDataSource
from app.domain import PlayerPosition, TrackingFrame
from app.engine.tracking import (
    compute_ball_zone_distribution,
    compute_formation,
    compute_pressure,
)


def test_player_position_validates_bounds():
    from pydantic import ValidationError

    PlayerPosition(player_external_id=1, x=50.0, y=50.0)
    with pytest.raises(ValidationError):
        PlayerPosition(player_external_id=1, x=150.0, y=0.0)  # x > 100


def test_tracking_frame_holds_player_positions():
    frame = TrackingFrame(
        sport="football",
        match_external_id=1,
        timestamp=datetime.now(UTC),
        period=1,
        minute=12.5,
        players=(
            PlayerPosition(player_external_id=10, x=20.0, y=50.0),
            PlayerPosition(player_external_id=11, x=80.0, y=45.0),
        ),
    )
    assert len(frame.players) == 2
    assert frame.players[0].player_external_id == 10


def test_tracking_data_source_is_abstract():
    with pytest.raises(TypeError):
        TrackingDataSource()  # type: ignore[abstract]


def test_engine_tracking_stubs_raise_until_faz_6():
    with pytest.raises(NotImplementedError, match="Faz 6"):
        compute_pressure(611, [])
    with pytest.raises(NotImplementedError, match="Faz 6"):
        compute_formation(611, [])


def _frame_with_ball_at(x: float) -> TrackingFrame:
    return TrackingFrame(
        sport="football",
        match_external_id=1,
        timestamp=datetime.now(UTC),
        period=1,
        minute=10.0,
        ball=PlayerPosition(player_external_id=0, x=x, y=50.0),
        players=(),
    )


def test_ball_zone_distribution_empty_frames():
    r = compute_ball_zone_distribution([]).value
    assert r.total_frames == 0
    assert r.frames_with_ball == 0
    assert r.defensive_third_fraction == 0.0


def test_ball_zone_distribution_skips_frames_without_ball():
    frames = [
        TrackingFrame(
            sport="football", match_external_id=1,
            timestamp=datetime.now(UTC), period=1, minute=10.0,
            ball=None, players=(),
        ),
        _frame_with_ball_at(50.0),
    ]
    r = compute_ball_zone_distribution(frames).value
    assert r.total_frames == 2
    assert r.frames_with_ball == 1
    assert r.middle_third_fraction == 1.0


def test_ball_zone_distribution_partitions_thirds():
    """3 frame defensive (x<33), 4 frame middle (33<x<66), 3 frame attacking (x>66)."""
    frames = (
        [_frame_with_ball_at(10.0)] * 3
        + [_frame_with_ball_at(50.0)] * 4
        + [_frame_with_ball_at(80.0)] * 3
    )
    r = compute_ball_zone_distribution(frames).value
    assert r.total_frames == 10
    assert r.frames_with_ball == 10
    assert r.defensive_third_fraction == 0.3
    assert r.middle_third_fraction == 0.4
    assert r.attacking_third_fraction == 0.3


def test_ball_zone_distribution_v1_audit():
    r = compute_ball_zone_distribution([_frame_with_ball_at(20.0)])
    assert r.audit.engine_version == "1"
    assert r.audit.metric == "ball_zone_distribution"
    assert "fractions" in r.audit.formula
