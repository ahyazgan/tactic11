"""/teams/batch endpoint — multi-team analiz tek istekte (PR D3)."""

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


def _seed(session, base: datetime):
    session.add_all([
        models.Match(
            sport=football.SPORT_NAME, external_id=1, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=607,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=2, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=607, away_team_external_id=614,
            home_score=1, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203, season=2024,
            kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
        ),
    ])
    session.flush()


def test_batch_returns_per_team_form_and_rating(session, client):
    _seed(session, datetime.now(UTC))
    r = client.get("/teams/batch?ids=611,607")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"611", "607"}
    assert "form" in body["611"]
    assert "rating" in body["611"]
    # form audit doğru engine
    assert body["611"]["form"]["audit"]["engine"] == "engine.form"


def test_batch_inline_error_for_unknown_team(session, client):
    _seed(session, datetime.now(UTC))
    r = client.get("/teams/batch?ids=611,999999")
    assert r.status_code == 200
    body = r.json()
    assert body["611"].get("form") is not None
    assert body["999999"]["error"] == "no_matches"


def test_batch_include_filter_excludes_unrequested(session, client):
    _seed(session, datetime.now(UTC))
    r = client.get("/teams/batch?ids=611&include=rating")
    body = r.json()
    assert "rating" in body["611"]
    assert "form" not in body["611"]
    assert "schedule" not in body["611"]


def test_batch_include_schedule_works(session, client):
    _seed(session, datetime.now(UTC))
    r = client.get("/teams/batch?ids=611&include=schedule")
    body = r.json()
    assert body["611"]["schedule"]["audit"]["engine"] == "engine.schedule"


def test_batch_rejects_invalid_ids(client):
    r = client.get("/teams/batch?ids=abc,def")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_ids"


def test_batch_rejects_empty_ids(client):
    r = client.get("/teams/batch?ids=,,")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "empty_ids"


def test_batch_rejects_more_than_20_ids(client):
    ids = ",".join(str(i) for i in range(1, 25))  # 24 id
    r = client.get(f"/teams/batch?ids={ids}")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "too_many_ids"


def test_batch_rejects_invalid_include_engine(client):
    r = client.get("/teams/batch?ids=611&include=form,bogus")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_include"
    assert "bogus" in body["error"]["message"]
