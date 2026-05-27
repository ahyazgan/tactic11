"""Tracking iskeletinin import edilebildiğini ve sözleşmeyi koruduğunu doğrula.

Bu modüller Faz 6'da gerçek implementasyonla doldurulacak; o güne kadar
şekilleri stabil kalsın.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.data.sources.tracking import TrackingDataSource
from app.domain import PlayerPosition, TrackingFrame
from app.engine.tracking import compute_formation, compute_pressure


def test_player_position_validates_bounds():
    PlayerPosition(player_external_id=1, x=50.0, y=50.0)
    with pytest.raises(Exception):
        PlayerPosition(player_external_id=1, x=150.0, y=0.0)  # x > 100


def test_tracking_frame_holds_player_positions():
    frame = TrackingFrame(
        sport="football",
        match_external_id=1,
        timestamp=datetime.now(timezone.utc),
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
