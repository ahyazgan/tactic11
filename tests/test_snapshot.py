from __future__ import annotations

from datetime import UTC, datetime

from app.db import models
from app.snapshot import build_scope, get_latest_snapshot, save_snapshot
from app.sports import football


def _seed(session):
    session.add_all(
        [
            models.League(
                sport=football.SPORT_NAME,
                external_id=203,
                name="Süper Lig",
                season=2024,
                country="Turkey",
            ),
            models.Match(
                sport=football.SPORT_NAME,
                external_id=1,
                league_external_id=203,
                season=2024,
                kickoff=datetime(2024, 8, 10, 18, 0, tzinfo=UTC),
                status="FT",
                home_team_external_id=611,
                away_team_external_id=607,
                home_score=2,
                away_score=1,
            ),
            models.Match(
                sport=football.SPORT_NAME,
                external_id=2,
                league_external_id=203,
                season=2024,
                kickoff=datetime(2024, 8, 17, 18, 0, tzinfo=UTC),
                status="FT",
                home_team_external_id=614,
                away_team_external_id=611,
                home_score=0,
                away_score=3,
            ),
        ]
    )
    session.flush()


def test_save_counts_distinct_teams_from_matches(session):
    _seed(session)
    snap = save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    assert snap.leagues_count == 1
    assert snap.teams_count == 3  # 611, 607, 614
    assert snap.matches_count == 2
    assert snap.scope == build_scope(203, 2024)


def test_history_preserved_not_overwritten(session):
    _seed(session)
    s1 = save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    s2 = save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    assert s1.id != s2.id

    latest = get_latest_snapshot(
        session, sport=football.SPORT_NAME, scope=build_scope(203, 2024)
    )
    assert latest is not None
    assert latest.id == s2.id
