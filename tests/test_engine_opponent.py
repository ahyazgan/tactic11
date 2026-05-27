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


# ---- v2 alanları -----------------------------------------------------------


def test_h2h_clean_sheets_per_team():
    matches = [
        _match(1, 611, 607, 2, 0, 30),  # A clean sheet
        _match(2, 607, 611, 0, 1, 20),  # A clean sheet (A=away, b_goal=0)
        _match(3, 611, 607, 3, 1, 10),  # ne A ne B clean
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.team_a_clean_sheets == 2
    assert h.team_b_clean_sheets == 0


def test_h2h_home_away_split_for_team_a():
    matches = [
        _match(1, 611, 607, 2, 0, 30),  # A ev sahibi galip
        _match(2, 607, 611, 0, 1, 20),  # A deplasman galip
        _match(3, 611, 607, 0, 1, 10),  # B galip
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.team_a_wins == 2
    assert h.team_a_home_wins == 1
    assert h.team_a_away_wins == 1


def test_h2h_last_meeting_returns_latest_iso():
    matches = [
        _match(1, 611, 607, 2, 0, 30),
        _match(2, 607, 611, 0, 1, 5),  # en yeni
        _match(3, 611, 607, 1, 1, 20),
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.last_meeting_kickoff is not None
    # En yeni = 5 gün önce; ISO formatında olmalı
    assert "T" in h.last_meeting_kickoff
    # 5 gün önceki maç: 607 home, A away, A galip → "team_a"
    assert h.last_meeting_result == "team_a"


def test_h2h_no_matches_has_none_last_meeting():
    h = compute_head_to_head(611, 607, []).value
    assert h.matches_played == 0
    assert h.last_meeting_kickoff is None
    assert h.last_meeting_result is None
    assert h.team_a_clean_sheets == 0
    assert h.team_b_clean_sheets == 0
    # v3 alanları: empty case
    assert h.avg_goals_per_match == 0.0
    assert h.biggest_a_win_margin == 0
    assert h.recent_a_wins == 0


def test_h2h_avg_goals_per_match():
    matches = [
        _match(1, 611, 607, 2, 1, 30),  # 3 gol
        _match(2, 607, 611, 0, 0, 10),  # 0 gol
        _match(3, 611, 607, 1, 2, 5),   # 3 gol
    ]
    h = compute_head_to_head(611, 607, matches).value
    # Toplam 6 gol / 3 maç = 2.0
    assert h.avg_goals_per_match == 2.0


def test_h2h_biggest_win_margins():
    matches = [
        _match(1, 611, 607, 5, 0, 30),  # A wins by 5
        _match(2, 611, 607, 2, 1, 20),  # A wins by 1
        _match(3, 607, 611, 4, 0, 10),  # B wins by 4 (607 home, A away 0-4)
    ]
    h = compute_head_to_head(611, 607, matches).value
    assert h.biggest_a_win_margin == 5
    assert h.biggest_b_win_margin == 4


def test_h2h_recent_trend_isolates_last_3():
    """10 maçta dengeli ama son 3'te A dominant — recent_a_wins göstermeli."""
    # 7 eski maç: A 2, B 2, draw 3 (dengeli)
    matches = []
    matches += [_match(i, 611, 607, 1, 2, 100 - i) for i in range(1, 3)]  # 2 B wins
    matches += [_match(i, 611, 607, 2, 1, 100 - i) for i in range(3, 5)]  # 2 A wins
    matches += [_match(i, 611, 607, 1, 1, 100 - i) for i in range(5, 8)]  # 3 draws
    # Son 3 maç: A 3, daha yeni tarihlere
    matches += [_match(i, 611, 607, 3, 0, 20 - i) for i in range(8, 11)]  # 3 A wins
    h = compute_head_to_head(611, 607, matches).value
    assert h.matches_played == 10
    # Overall: 5 A wins (2 eski + 3 yeni), 2 B wins, 3 draws
    assert h.team_a_wins == 5
    # Recent (son 3 = son 3 maç): hepsi A
    assert h.recent_a_wins == 3
    assert h.recent_b_wins == 0
    assert h.recent_draws == 0


def test_h2h_v3_audit_includes_recent_window():
    matches = [_match(1, 611, 607, 1, 0, 5)]
    res = compute_head_to_head(611, 607, matches)
    assert res.audit.engine_version == "3"
    assert res.audit.inputs["recent_window"] == 3
    assert "biggest" in res.audit.formula
