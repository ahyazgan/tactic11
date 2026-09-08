"""/tracking endpoint'leri — saha overlay'inin frame servisi."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import models
from app.db.session import get_session
from app.sports import football


@pytest.fixture()
def client(session):
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(session, match_id: int = 9600, frames: int = 3):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=11, season=90,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=217, away_team_external_id=213,
        home_score=1, away_score=1, tenant_id="t-default",
    ))
    base = datetime(2000, 1, 1, tzinfo=UTC)
    for i in range(frames):
        minute = 10.0 * (i + 1)
        session.add(models.TrackingFrameRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            match_external_id=match_id,
            timestamp=base + timedelta(minutes=minute),
            period=1 if minute < 45 else 2, minute=minute,
            ball_x=50.0 + i, ball_y=40.0,
            players_json=json.dumps([
                {"player_external_id": 5503, "x": 50.0 + i, "y": 40.0,
                 "velocity_mps": None, "team_external_id": 217,
                 "is_actor": True, "is_keeper": False, "identity_estimated": False},
                {"player_external_id": 20001, "x": 60.0, "y": 45.0,
                 "velocity_mps": None, "team_external_id": 213,
                 "is_actor": False, "is_keeper": False, "identity_estimated": True},
            ]),
            meta_json=json.dumps({
                "source": "statsbomb_360", "event_uuid": f"u{i}",
                "event_type": "Pass", "possession_team_external_id": 217,
                "visible_area": [[0, 0], [100, 0], [100, 100], [0, 100]],
            }),
            created_at=now,
        ))
    session.commit()


def test_matches_list_groups_by_match_with_source(session, client):
    _seed(session)
    r = client.get("/tracking/matches")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    m = body["matches"][0]
    assert m["match_id"] == 9600
    assert m["frames"] == 3
    assert m["source"] == "statsbomb_360"
    assert m["home_team_external_id"] == 217
    assert m["score"] == "1-1"


def test_matches_list_empty(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    assert client.get("/tracking/matches").json() == {"matches": [], "total": 0}


def test_status_404_when_match_missing(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    assert client.get("/tracking/matches/424242/status").status_code == 404


def test_status_reports_range_and_source(session, client):
    _seed(session)
    r = client.get("/tracking/matches/9600/status")
    assert r.status_code == 200
    body = r.json()
    assert body["frames"] == 3
    assert body["first_minute"] == 10.0
    assert body["last_minute"] == 30.0
    assert body["source"] == "statsbomb_360"
    assert body["home_team_external_id"] == 217


def test_status_empty_when_no_frames(session, client):
    _seed(session, frames=0)
    body = client.get("/tracking/matches/9600/status").json()
    assert body["frames"] == 0
    assert body["source"] is None
    assert body["first_minute"] is None


def test_frame_at_returns_latest_before_minute(session, client):
    _seed(session)
    r = client.get("/tracking/matches/9600/frame?minute=25")
    assert r.status_code == 200
    body = r.json()
    frame = body["frame"]
    assert frame["minute"] == 20.0
    assert frame["event_uuid"] == "u1"
    assert frame["ball"] == {"x": 51.0, "y": 40.0}
    assert frame["visible_area"][2] == [100, 100]
    actor = next(p for p in frame["players"] if p["is_actor"])
    assert actor["player_external_id"] == 5503
    assert actor["identity_estimated"] is False
    other = next(p for p in frame["players"] if not p["is_actor"])
    assert other["identity_estimated"] is True


def test_frame_at_before_first_frame_is_none(session, client):
    _seed(session)
    body = client.get("/tracking/matches/9600/frame?minute=5").json()
    assert body["frame"] is None


def test_frames_between_filters_and_limits(session, client):
    _seed(session)
    body = client.get("/tracking/matches/9600/frames?from_minute=15&to_minute=35&limit=5").json()
    assert body["count"] == 2
    assert [f["minute"] for f in body["frames"]] == [20.0, 30.0]
    # limit aşılınca en güncel kareler korunur, sıralama yine artan
    body = client.get("/tracking/matches/9600/frames?from_minute=0&to_minute=90&limit=2").json()
    assert body["count"] == 2
    assert [f["minute"] for f in body["frames"]] == [20.0, 30.0]


def test_frames_between_rejects_inverted_range(session, client):
    _seed(session)
    r = client.get("/tracking/matches/9600/frames?from_minute=50&to_minute=10")
    assert r.status_code == 422
