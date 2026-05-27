from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.opponent import compute_head_to_head
from app.sports import football


def _match(ext_id, home, away, hs, as_, days_ago=1, status="FT"):
    return Match(
        sport=football.SPORT_NAME,
        external_id=ext_id,
        league_external_id=203,
        season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
        status=status,
        home_team_external_id=home,
        away_team_external_id=away,
        home_score=hs,
        away_score=as_,
    )


def test_h2h_aggregates_correctly_both_home_and_away():
    matches = [
        _match(1, 611, 607, 2, 1, 30),   # A wins (home)
        _match(2, 607, 611, 0, 0, 20),   # draw (A away)
        _match(3, 611, 607, 1, 2, 10),   # B wins (B at A's home)
        _match(4, 998, 611, 0, 0, 5),    # alakasız, eklenmemeli
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.matches_played == 3
    assert (h.team_a_wins, h.draws, h.team_b_wins) == (1, 1, 1)
    assert h.team_a_goals == 3
    assert h.team_b_goals == 3


def test_h2h_rejects_self_pair():
    with pytest.raises(ValueError):
        compute_head_to_head(611, 611, [])


def test_h2h_ignores_unfinished():
    matches = [
        _match(1, 611, 607, None, None, 5, status="NS"),
        _match(2, 607, 611, 1, 0, 1),
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.matches_played == 1
    assert h.team_b_wins == 1
