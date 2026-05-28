"""engine.defensive_duels tests."""

from __future__ import annotations

import pytest

from app.domain import DefensiveAction
from app.engine.defensive_duels import compute_defensive_duels


def _d(team: int, player: int = 1, action: str = "tackle",
       successful: bool = True) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=10.0, period=1,
        x=50, y=50, action_type=action,  # type: ignore[arg-type]
        successful=successful,
    )


def test_team_high_win_rate():
    defs = [_d(11, successful=True) for _ in range(8)] + [_d(11, successful=False)] * 2
    r = compute_defensive_duels(team_external_id=11, all_def_actions=defs).value
    assert r.total_duels == 10
    assert r.duels_won == 8
    assert r.win_rate == 0.8


def test_player_filter():
    defs = [
        _d(11, player=100, successful=True),
        _d(11, player=100, successful=True),
        _d(11, player=200, successful=False),  # farklı oyuncu
    ]
    r = compute_defensive_duels(player_external_id=100, all_def_actions=defs).value
    assert r.total_duels == 2
    assert r.win_rate == 1.0


def test_non_duel_actions_excluded():
    """interception duel değil."""
    defs = [_d(11, action="interception")]
    r = compute_defensive_duels(team_external_id=11, all_def_actions=defs).value
    assert r.total_duels == 0


def test_no_subject_raises():
    with pytest.raises(ValueError, match="verilmeli"):
        compute_defensive_duels(all_def_actions=[])
