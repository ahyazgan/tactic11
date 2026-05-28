"""Tactical profile cache + cache-clear endpoint tests."""

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


def _seed_with_events(session, *, team_id: int = 11, match_id: int = 6001):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=team_id, away_team_external_id=22,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    for i in range(20):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=team_id,
            player_external_id=1, event_type="pass",
            minute=float(10 + i), period=1,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i // 3, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    session.commit()


def test_first_call_not_cached(session, client):
    _seed_with_events(session)
    r = client.get("/admin/teams/11/tactical-profile")
    assert r.status_code == 200
    assert r.json().get("_cached") is False


def test_second_call_hits_cache(session, client):
    _seed_with_events(session)
    r1 = client.get("/admin/teams/11/tactical-profile")
    assert r1.json()["_cached"] is False
    r2 = client.get("/admin/teams/11/tactical-profile")
    assert r2.json()["_cached"] is True


def test_cache_keyed_by_last_n(session, client):
    """Farklı last_n parametresi → ayrı cache key."""
    _seed_with_events(session)
    client.get("/admin/teams/11/tactical-profile?last_n=10")
    r = client.get("/admin/teams/11/tactical-profile?last_n=5")
    # last_n=5 ilk kez çağrıldı, cache miss
    assert r.json()["_cached"] is False


def test_use_cache_false_bypasses(session, client):
    _seed_with_events(session)
    client.get("/admin/teams/11/tactical-profile")  # ısıtma
    r = client.get("/admin/teams/11/tactical-profile?use_cache=false")
    assert r.json()["_cached"] is False


def test_cache_clear_endpoint(session, client):
    _seed_with_events(session)
    client.get("/admin/teams/11/tactical-profile")
    # 1 cache satırı var
    n_before = session.query(models.CacheEntry).filter_by(
        source="tactical_profile",
    ).count()
    assert n_before == 1

    r = client.post("/admin/tactical-cache/clear")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    n_after = session.query(models.CacheEntry).filter_by(
        source="tactical_profile",
    ).count()
    assert n_after == 0
