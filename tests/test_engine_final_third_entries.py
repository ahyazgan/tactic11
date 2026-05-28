"""engine.final_third_entries tests."""

from __future__ import annotations

from app.domain import Carry, PassEvent
from app.engine.final_third_entries import compute_final_third_entries


def _p(team: int, sx: float, ex: float, ey: float = 50) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
    )


def _c(team: int, sx: float, ex: float, ey: float = 50) -> Carry:
    return Carry(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
    )


def test_pass_entry_into_final_third():
    passes = [_p(11, 50, 70)]  # 50 < 66.7, 70 ≥ 66.7
    r = compute_final_third_entries(11, passes, []).value
    assert r.pass_entries == 1
    assert r.total_entries == 1


def test_carry_entry():
    carries = [_c(11, 50, 70)]
    r = compute_final_third_entries(11, [], carries).value
    assert r.carry_entries == 1


def test_pass_already_in_final_third_not_entry():
    """Pas zaten final third'da başlıyorsa entry sayılmaz."""
    passes = [_p(11, 70, 90)]
    r = compute_final_third_entries(11, passes, []).value
    assert r.pass_entries == 0


def test_dominant_channel_right():
    passes = [_p(11, 50, 70, ey=80) for _ in range(5)]  # sağ kanal
    r = compute_final_third_entries(11, passes, []).value
    assert r.dominant_entry_channel == "right"


def test_balanced_distribution():
    passes = (
        [_p(11, 50, 70, ey=15) for _ in range(3)] +
        [_p(11, 50, 70, ey=50) for _ in range(3)] +
        [_p(11, 50, 70, ey=85) for _ in range(3)]
    )
    r = compute_final_third_entries(11, passes, []).value
    assert r.dominant_entry_channel == "balanced"


def test_opponent_excluded():
    passes = [_p(22, 50, 70)]
    r = compute_final_third_entries(11, passes, []).value
    assert r.total_entries == 0
