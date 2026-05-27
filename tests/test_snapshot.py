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


def test_get_snapshot_at_or_before_returns_closest_earlier(session):
    from datetime import datetime, timedelta

    from app.db import models
    from app.snapshot import get_snapshot_at_or_before

    base = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    scope = build_scope(203, 2024)
    session.add_all([
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=base,
            leagues_count=1, teams_count=10, matches_count=50,
        ),
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=base + timedelta(days=7),
            leagues_count=1, teams_count=12, matches_count=80,
        ),
        models.Snapshot(
            sport=football.SPORT_NAME, scope=scope, created_at=base + timedelta(days=14),
            leagues_count=1, teams_count=14, matches_count=110,
        ),
    ])
    session.flush()

    # 10 gün sonrası → 7. günü dönmeli (en yakın <= baseline)
    target = base + timedelta(days=10)
    snap = get_snapshot_at_or_before(session, sport=football.SPORT_NAME, scope=scope, ts=target)
    assert snap is not None
    assert snap.teams_count == 12

    # base'den önce → None
    snap_too_early = get_snapshot_at_or_before(
        session, sport=football.SPORT_NAME, scope=scope, ts=base - timedelta(days=1),
    )
    assert snap_too_early is None


def test_diff_snapshots_computes_delta(session):
    from datetime import datetime, timedelta

    from app.db import models
    from app.snapshot import diff_snapshots

    base = datetime(2024, 6, 1, tzinfo=UTC)
    earlier = models.Snapshot(
        sport=football.SPORT_NAME, scope="x", created_at=base,
        leagues_count=1, teams_count=18, matches_count=100,
    )
    later = models.Snapshot(
        sport=football.SPORT_NAME, scope="x", created_at=base + timedelta(days=7),
        leagues_count=1, teams_count=20, matches_count=145,
    )
    session.add_all([earlier, later])
    session.flush()

    d = diff_snapshots(earlier, later)
    assert d["delta"]["leagues_count"] == 0
    assert d["delta"]["teams_count"] == 2
    assert d["delta"]["matches_count"] == 45
    assert d["delta"]["elapsed_seconds"] == 7 * 86400
    assert d["from"]["id"] == earlier.id
    assert d["to"]["id"] == later.id
