"""/players/{id}/season-stats endpoint testleri — sezon toplam + emsal havuzu."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _app_row(player_id: int, match_id: int, days_ago: int, **stats):
    now = datetime.now(UTC)
    return models.PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        minutes=stats.pop("minutes", 90),
        kickoff=now - timedelta(days=days_ago),
        team_external_id=stats.pop("team_external_id", 611),
        **stats,
    )


def test_season_stats_404_when_no_appearances(client):
    r = client.get("/players/424242/season-stats")
    assert r.status_code == 404


def test_season_stats_aggregates_player_totals(session, client):
    session.add_all([
        _app_row(
            10, 1, 7, goals=1, assists=0, shots_total=3, shots_on=2,
            passes_total=40, passes_accuracy=90, key_passes=2,
            dribbles_attempts=4, dribbles_success=3,
            tackles_total=2, interceptions=1, duels_total=10, duels_won=6,
            fouls_committed=1,
        ),
        _app_row(
            10, 2, 3, goals=2, assists=1, shots_total=5, shots_on=4,
            passes_total=60, passes_accuracy=80, key_passes=3,
            dribbles_attempts=6, dribbles_success=4,
            tackles_total=1, interceptions=2, duels_total=12, duels_won=7,
            fouls_committed=2,
        ),
        # Oynamadığı maç (minutes=0) appearances sayısına girmemeli
        _app_row(10, 3, 1, minutes=0),
    ])
    session.flush()

    r = client.get("/players/10/season-stats?include_peers=false")
    assert r.status_code == 200
    p = r.json()["value"]["player"]
    assert p["player_id"] == 10
    assert p["appearances"] == 2          # minutes>0 olanlar
    assert p["minutes"] == 180
    assert p["goals"] == 3
    assert p["assists"] == 1
    assert p["shots"] == 8
    assert p["shots_on"] == 6
    assert p["key_passes"] == 5
    assert p["dribbles_att"] == 10
    assert p["dribbles_succ"] == 7
    assert p["tackles"] == 3
    assert p["interceptions"] == 3
    assert p["duels"] == 22
    assert p["duels_won"] == 13
    assert p["fouls"] == 3
    # Pas isabeti hacim-ağırlıklı: (40*90 + 60*80) / 100 = 84
    assert p["pass_accuracy"] == 84


def test_season_stats_includes_team_peers(session, client):
    session.add_all([
        _app_row(20, 11, 5, goals=1, team_external_id=611),
        _app_row(21, 11, 5, goals=0, tackles_total=4, team_external_id=611),
        # Başka takımın oyuncusu — havuza girmemeli
        _app_row(30, 12, 5, goals=2, team_external_id=999),
    ])
    session.flush()

    r = client.get("/players/20/season-stats")
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["team_external_id"] == 611
    peer_ids = {p["player_id"] for p in v["peers"]}
    assert peer_ids == {20, 21}


def test_season_stats_goalkeeper_clean_sheets(session, client):
    session.add_all([
        _app_row(40, 21, 9, saves=4, goals_conceded=0),
        _app_row(40, 22, 6, saves=2, goals_conceded=2),
        _app_row(40, 23, 2, saves=5, goals_conceded=0),
    ])
    session.flush()

    r = client.get("/players/40/season-stats?include_peers=false")
    p = r.json()["value"]["player"]
    assert p["saves"] == 11
    assert p["goals_conceded"] == 2
    assert p["clean_sheets"] == 2
