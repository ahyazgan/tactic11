"""Fiziksel yük: düzeltilmiş hız, hız bölgeleri, kapsama ve takım ayrımı."""
from __future__ import annotations

import math

import pytest

from app.engine.tracking.physical_load import (
    MAX_GAP_SECONDS,
    compute_physical_load,
    rates,
    total_load,
    track_steps,
)

HOME, AWAY = 11, 22
FPS = 5


def _run(speed: float, seconds: float, team: int | None, t0: float = 0.0, jitter: float = 0.0) -> list:
    n = int(seconds * FPS) + 1
    return [(t0 + i / FPS, 10.0 + speed * i / FPS, 30.0 + (jitter if i % 2 else -jitter), team) for i in range(n)]


def test_steady_run_gives_its_speed_and_zone():
    load = rates(total_load({1: _run(6.0, 60.0, HOME)}))
    assert load["m_per_player_min"] == pytest.approx(360.0, rel=0.02)
    assert load["hsr_share"] > 0.97 and load["sprint_share"] == 0.0
    assert rates(total_load({1: _run(8.0, 60.0, HOME)}))["sprint_share"] > 0.97


def test_smoothing_removes_position_jitter_that_raw_speed_would_count():
    samples = _run(0.0, 60.0, HOME, jitter=0.4)
    raw = sum(math.dist(a[1:3], b[1:3]) for a, b in zip(samples, samples[1:], strict=False))
    smooth = total_load({1: samples})["distance_m"]
    assert raw > 200.0 and smooth < 0.2 * raw
    assert rates(total_load({1: samples}))["hsr_share"] == 0.0


def test_gaps_and_identity_jumps_are_not_counted_as_running():
    first, second = _run(2.0, 10.0, HOME), _run(2.0, 10.0, HOME, t0=10.0 + MAX_GAP_SECONDS + 1)
    assert total_load({1: first + second})["seconds"] == pytest.approx(20.0, abs=0.01)
    jumped = first + [(t, x + 60.0, y, team) for t, x, y, team in _run(2.0, 10.0, HOME, t0=10.2)]
    steps = track_steps(jumped)
    assert max(dist / dt for _mid, dt, dist, _team in steps) <= 12.0
    assert track_steps(first[:2]) == []


def test_slices_split_by_team_and_mark_low_coverage_unreliable():
    tracks = {i: _run(3.0, 300.0, HOME) for i in range(8)}
    tracks |= {100 + i: _run(1.0, 300.0, AWAY) for i in range(3)}
    tracks[999] = _run(9.0, 300.0, None)
    report = compute_physical_load(tracks, HOME, AWAY, [(0.0, 5.0), (5.0, 10.0)])
    first = report["slices"][0]
    assert first["home"]["reliable"] and first["home"]["coverage"] == pytest.approx(8 / 11, abs=0.01)
    assert first["home"]["m_per_player_min"] == pytest.approx(180.0, rel=0.02)
    assert not first["away"]["reliable"] and first["away"]["m_per_player_min"] == pytest.approx(60.0, rel=0.02)
    assert report["slices"][1]["home"]["m_per_player_min"] is None
    assert report["teams"]["home"]["player_minutes"] == pytest.approx(40.0, abs=0.2)
    assert report["teams"]["away"] is None and report["limits"]
