"""FixtureTrackingSource — lokal JSON tracking adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data.sources.fixture_tracking import (
    FixtureTrackingSource,
    TrackingFixtureMissing,
)
from app.data.sources.tracking import TrackingDataSource
from app.domain import TrackingFrame
from app.engine.tracking import compute_ball_zone_distribution


def test_is_tracking_data_source_subclass():
    """ABC sözleşmesi: vendor adapter geldiğinde swap edebilelim."""
    assert issubclass(FixtureTrackingSource, TrackingDataSource)


def test_get_frames_for_match_99_returns_30_frames():
    """Repo'daki tracking_99.json'ı okur (generate_tracking_fixture.py çıktısı)."""
    src = FixtureTrackingSource()
    frames = list(src.get_match_frames(99))
    assert len(frames) == 30
    assert all(isinstance(f, TrackingFrame) for f in frames)
    # Her frame ev 11 + dep 11 = 22 oyuncu + top
    assert all(len(f.players) == 22 for f in frames)
    assert all(f.ball is not None for f in frames)
    # match_external_id adapter tarafından enjekte edildi
    assert {f.match_external_id for f in frames} == {99}


def test_missing_fixture_raises(tmp_path: Path):
    src = FixtureTrackingSource(fixture_dir=tmp_path)
    with pytest.raises(TrackingFixtureMissing, match="tracking_42"):
        list(src.get_match_frames(42))


def test_has_fixture_checks_existence(tmp_path: Path):
    src = FixtureTrackingSource(fixture_dir=tmp_path)
    assert src.has_fixture(7) is False
    (tmp_path / "tracking_7.json").write_text(
        json.dumps({"match_external_id": 7, "frames": []}), encoding="utf-8"
    )
    assert src.has_fixture(7) is True


def test_period_filter_returns_only_matching_period(tmp_path: Path):
    payload = {
        "match_external_id": 5,
        "sport": "football",
        "frames": [
            {
                "timestamp": "2024-08-15T18:00:00+00:00",
                "period": 1, "minute": 10.0,
                "ball": {"player_external_id": 0, "x": 30.0, "y": 50.0},
                "players": [],
            },
            {
                "timestamp": "2024-08-15T19:00:00+00:00",
                "period": 2, "minute": 55.0,
                "ball": {"player_external_id": 0, "x": 70.0, "y": 50.0},
                "players": [],
            },
        ],
    }
    (tmp_path / "tracking_5.json").write_text(json.dumps(payload), encoding="utf-8")
    src = FixtureTrackingSource(fixture_dir=tmp_path)
    p2 = list(src.get_match_frames(5, period=2))
    assert len(p2) == 1
    assert p2[0].period == 2


def test_frame_without_ball_loads_as_none(tmp_path: Path):
    payload = {
        "match_external_id": 1,
        "sport": "football",
        "frames": [{
            "timestamp": "2024-08-15T18:00:00+00:00",
            "period": 1, "minute": 0.0,
            "ball": None,
            "players": [{"player_external_id": 9, "x": 50.0, "y": 50.0}],
        }],
    }
    (tmp_path / "tracking_1.json").write_text(json.dumps(payload), encoding="utf-8")
    src = FixtureTrackingSource(fixture_dir=tmp_path)
    frames = list(src.get_match_frames(1))
    assert frames[0].ball is None
    assert frames[0].players[0].player_external_id == 9


def test_velocity_optional(tmp_path: Path):
    payload = {
        "match_external_id": 1,
        "sport": "football",
        "frames": [{
            "timestamp": "2024-08-15T18:00:00+00:00",
            "period": 1, "minute": 0.0,
            "ball": {"player_external_id": 0, "x": 50.0, "y": 50.0, "velocity_mps": 12.5},
            "players": [{"player_external_id": 9, "x": 50.0, "y": 50.0}],
        }],
    }
    (tmp_path / "tracking_1.json").write_text(json.dumps(payload), encoding="utf-8")
    src = FixtureTrackingSource(fixture_dir=tmp_path)
    frames = list(src.get_match_frames(1))
    assert frames[0].ball is not None
    assert frames[0].ball.velocity_mps == 12.5
    assert frames[0].players[0].velocity_mps is None


def test_integration_with_compute_ball_zone_distribution():
    """Adapter + engine.tracking entegrasyon: 30 frame → ball zone raporu."""
    src = FixtureTrackingSource()
    frames = src.get_match_frames(99)
    result = compute_ball_zone_distribution(frames)
    v = result.value
    assert v.total_frames == 30
    assert v.frames_with_ball == 30
    # Generator topu orta-üçten hücum-üçüne taşıyor — attacking baskın olmalı
    fractions = (
        v.defensive_third_fraction,
        v.middle_third_fraction,
        v.attacking_third_fraction,
    )
    assert sum(fractions) == pytest.approx(1.0, abs=1e-4)
    # Generator yörüngesi 40→75 arası: defansif üçte hiç olmamalı
    assert v.defensive_third_fraction == 0.0
    assert v.attacking_third_fraction > 0.0
