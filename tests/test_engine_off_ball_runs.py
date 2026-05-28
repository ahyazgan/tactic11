"""engine.off_ball_runs tests."""

from __future__ import annotations

from app.domain import Carry, PassEvent
from app.engine.off_ball_runs import compute_off_ball_runs


def _carry(player: int, sx: float, ex: float, ey: float = 50) -> Carry:
    return Carry(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
    )


def _p(team: int, poss: int) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=50, start_y=50, end_x=55, end_y=50,
        possession_id=poss,
    )


def test_significant_carries_counted():
    carries = [
        _carry(100, 30, 50),   # 20 birim ilerleme
        _carry(100, 40, 41),   # 1 birim — gürültü
    ]
    passes = [_p(11, 1), _p(11, 2)]
    r = compute_off_ball_runs(
        player_external_id=100, team_external_id=11,
        all_carries=carries, all_passes=passes,
        player_minutes_played=90.0,
    ).value
    assert r.player_carries == 1
    assert r.forward_runs == 1


def test_per_90_normalization():
    carries = [_carry(100, 30, 50) for _ in range(2)]  # 2 anlamlı carry
    passes = [_p(11, 1)]
    r = compute_off_ball_runs(
        player_external_id=100, team_external_id=11,
        all_carries=carries, all_passes=passes,
        player_minutes_played=45.0,  # yarı maç
    ).value
    assert r.forward_runs_per_90 == 4.0  # 2 / 45 × 90


def test_team_possessions_via_pass_ids():
    carries = [_carry(100, 30, 50)]
    passes = [_p(11, 1), _p(11, 1), _p(11, 2), _p(11, 3)]
    r = compute_off_ball_runs(
        player_external_id=100, team_external_id=11,
        all_carries=carries, all_passes=passes,
        player_minutes_played=90.0,
    ).value
    assert r.team_possessions == 3  # unique possession_ids


def test_zero_minutes_no_per_90():
    carries = [_carry(100, 30, 50)]
    r = compute_off_ball_runs(
        player_external_id=100, team_external_id=11,
        all_carries=carries, all_passes=[],
        player_minutes_played=0.0,
    ).value
    assert r.forward_runs_per_90 == 0.0


def test_other_player_excluded():
    carries = [_carry(200, 30, 50)]
    r = compute_off_ball_runs(
        player_external_id=100, team_external_id=11,
        all_carries=carries, all_passes=[],
        player_minutes_played=90.0,
    ).value
    assert r.player_carries == 0
