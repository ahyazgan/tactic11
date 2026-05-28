"""engine.progressive_passes tests."""

from __future__ import annotations

import pytest

from app.domain import PassEvent
from app.engine.progressive_passes import compute_progressive_passes


def _p(team: int, player: int, sx: float, ex: float,
       completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=50,
        completed=completed,
    )


def test_own_half_30_progression_is_prog():
    """Kendi yarısında 30+ birim ilerleme → progressive."""
    passes = [_p(11, 1, sx=10, ex=45)]  # 35 ilerleme
    r = compute_progressive_passes(team_external_id=11, all_passes=passes).value
    assert r.progressive_passes == 1


def test_middle_third_15_progression_is_prog():
    passes = [_p(11, 1, sx=55, ex=72)]  # 17 ilerleme middle → final third
    r = compute_progressive_passes(team_external_id=11, all_passes=passes).value
    assert r.progressive_passes == 1


def test_final_third_entry_auto_prog():
    """Final third'a giriş (start<66.7, end≥66.7) otomatik prog."""
    passes = [_p(11, 1, sx=60, ex=68)]  # sadece 8 birim ama eşik geçti
    r = compute_progressive_passes(team_external_id=11, all_passes=passes).value
    assert r.progressive_passes == 1


def test_backward_pass_not_prog():
    passes = [_p(11, 1, sx=80, ex=50)]
    r = compute_progressive_passes(team_external_id=11, all_passes=passes).value
    assert r.progressive_passes == 0


def test_incomplete_pass_not_prog():
    passes = [_p(11, 1, sx=10, ex=80, completed=False)]
    r = compute_progressive_passes(team_external_id=11, all_passes=passes).value
    assert r.progressive_passes == 0


def test_player_per_90_normalization():
    passes = [_p(11, 100, sx=10, ex=45) for _ in range(3)]
    r = compute_progressive_passes(
        player_external_id=100, all_passes=passes, player_minutes_played=45.0,
    ).value
    assert r.progressive_per_90 == 6.0  # 3 / 45 × 90


def test_no_subject_raises():
    with pytest.raises(ValueError, match="verilmeli"):
        compute_progressive_passes(all_passes=[])
