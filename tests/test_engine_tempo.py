"""engine.tempo tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.tempo import compute_tempo


def _p(team: int) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=50, start_y=50, end_x=55, end_y=50,
    )


def test_fast_tempo():
    """8+ pas/dakika → fast."""
    passes = [_p(11)] * 800  # 800 pas / 90 dk = 8.88 ppm
    r = compute_tempo(11, passes).value
    assert r.label == "fast"


def test_medium_tempo():
    passes = [_p(11)] * 540  # 6 ppm
    r = compute_tempo(11, passes).value
    assert r.label == "medium"


def test_slow_tempo():
    passes = [_p(11)] * 300  # 3.3 ppm
    r = compute_tempo(11, passes).value
    assert r.label == "slow"


def test_per_match_normalization():
    passes = [_p(11)] * 540  # 540 pas
    r = compute_tempo(11, passes, matches_analyzed=2).value
    # 540 / (90*2) = 3 ppm → slow
    assert r.passes_per_minute == 3.0


def test_opponent_excluded():
    passes = [_p(22)] * 100
    r = compute_tempo(11, passes).value
    assert r.total_passes == 0
    assert r.label == "insufficient_data"
