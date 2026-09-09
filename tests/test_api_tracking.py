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
    assert (frame["ball"]["x"], frame["ball"]["y"]) == (51.0, 40.0)
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


def test_identities_roundtrip_applies_to_frames_and_tracks(session, client):
    _seed(session)
    body = {"identities": [
        {"track_player_external_id": 20001, "player_name": "Ali Kaya", "jersey_number": 7, "player_external_id": 777},
    ]}
    r = client.put("/tracking/matches/9600/identities", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1 and r.json()["identities"][0]["player_name"] == "Ali Kaya"

    fr = client.get("/tracking/matches/9600/frame?minute=25").json()["frame"]
    mapped = next(p for p in fr["players"] if p.get("name") == "Ali Kaya")
    assert mapped["player_external_id"] == 777 and mapped["track_player_external_id"] == 20001
    assert mapped["identity_estimated"] is False and mapped["jersey_number"] == 7
    other = next(p for p in fr["players"] if p["player_external_id"] == 5503)
    assert "name" not in other

    tr = client.get("/tracking/matches/9600/tracks").json()
    assert tr["total"] == 2 and tr["frames"] == 3
    t = next(x for x in tr["tracks"] if x["player_external_id"] == 20001)
    assert t["identity"]["player_name"] == "Ali Kaya" and t["frames"] == 3
    actor = next(x for x in tr["tracks"] if x["player_external_id"] == 5503)
    assert actor["actor_frames"] == 3 and actor["identity"] is None

    # replace=True listede olmayanı siler; upsert isim günceller
    r = client.put("/tracking/matches/9600/identities", json={"replace": True, "identities": [
        {"track_player_external_id": 5503, "player_name": "Veli"},
    ]})
    assert r.json()["removed"] == 1 and r.json()["total"] == 1
    assert client.delete("/tracking/matches/9600/identities/5503").status_code == 200
    assert client.get("/tracking/matches/9600/identities").json()["total"] == 0
    assert client.delete("/tracking/matches/9600/identities/5503").status_code == 404


def _seed_shape(session, match_id: int = 9700):
    """İki takım 11'er oyuncu, top rakip (213) takımında → 217 için pres ölçülür."""
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X", settings_json="{}", active=True, created_at=now))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id, league_external_id=0, season=2026,
        kickoff=now, status="FT", home_team_external_id=217, away_team_external_id=213, tenant_id="t-default",
    ))
    def team(base, team_id, x0):
        pts = [(x0 - 11, 50)] + [(x0, y) for y in (15, 38, 62, 85)] + [(x0 + 11, y) for y in (30, 50, 70)] + [(x0 + 22, y) for y in (20, 50, 80)]
        return [{"player_external_id": base + i, "x": x, "y": y, "velocity_mps": 2.0, "team_external_id": team_id,
                 "is_actor": False, "is_keeper": False, "identity_estimated": True} for i, (x, y) in enumerate(pts)]
    base_ts = datetime(2000, 1, 1, tzinfo=UTC)
    for i in range(4):
        session.add(models.TrackingFrameRow(
            sport=football.SPORT_NAME, tenant_id="t-default", match_external_id=match_id,
            timestamp=base_ts + timedelta(seconds=10 * 60 + i), period=1, minute=10 + i / 60,
            ball_x=56.0, ball_y=50.0,   # 217'nin en ileri oyuncusundan ~4 m ileride
            players_json=json.dumps(team(30000, 217, 30) + team(31000, 213, 60)),
            meta_json=json.dumps({"source": "video_tracking", "event_type": "video_sample",
                                  "possession_team_external_id": 213, "ball_velocity_mps": 6.0}),
            created_at=now,
        ))
    session.commit()


def test_shape_endpoint_bridges_engine_tracking(session, client):
    _seed_shape(session)
    r = client.get("/tracking/matches/9700/shape?minute=10.1&window=1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["frames"] == 4
    home = body["teams"]["home"]
    assert home["team_external_id"] == 217
    assert home["shape"]["frames_used"] == 4 and home["shape"]["players_mean"] == 11.0
    assert home["shape"]["width_m"] > 40 and home["shape"]["depth_m"] > 25
    assert home["shape"]["formation"] == "4-3-3"
    # 213 topta → 217 pres ölçülür; 213 için pres karesi yok
    assert home["pressure"]["frames_used"] == 4 and home["pressure"]["nearest_mean_m"] > 0
    assert body["teams"]["away"]["pressure"]["frames_used"] == 0
    assert "formula" in home and "width" in home["formula"]["shape"]
    fr = client.get("/tracking/matches/9700/frame?minute=10.5").json()["frame"]
    assert fr["ball"]["velocity_mps"] == 6.0


def test_frames_between_rejects_inverted_range(session, client):
    _seed(session)
    r = client.get("/tracking/matches/9600/frames?from_minute=50&to_minute=10")
    assert r.status_code == 422
