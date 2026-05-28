"""engine.carries_into_final_third tests."""

from __future__ import annotations

import pytest

from app.domain import Carry
from app.engine.carries_into_final_third import compute_carries_into_final_third


def _c(team: int, player: int, sx: float, ex: float) -> Carry:
    return Carry(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=50,
    )


def test_deep_to_final_third_counted():
    carries = [_c(11, 100, sx=40, ex=70)]
    r = compute_carries_into_final_third(
        team_external_id=11, all_carries=carries,
    ).value
    assert r.deep_to_final_third == 1


def test_already_in_final_third_not_counted():
    """Carry hücum üçünde başlıyorsa sayılmaz."""
    carries = [_c(11, 100, sx=70, ex=90)]
    r = compute_carries_into_final_third(
        team_external_id=11, all_carries=carries,
    ).value
    assert r.deep_to_final_third == 0


def test_doesnt_reach_final_third():
    carries = [_c(11, 100, sx=20, ex=60)]
    r = compute_carries_into_final_third(
        team_external_id=11, all_carries=carries,
    ).value
    assert r.deep_to_final_third == 0


def test_player_per_90():
    carries = [_c(11, 100, sx=40, ex=70) for _ in range(2)]
    r = compute_carries_into_final_third(
        player_external_id=100, all_carries=carries, player_minutes_played=45.0,
    ).value
    assert r.per_90 == 4.0  # 2 / 45 × 90


def test_no_subject_raises():
    with pytest.raises(ValueError, match="verilmeli"):
        compute_carries_into_final_third(all_carries=[])
