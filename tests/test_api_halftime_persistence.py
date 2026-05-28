"""Halftime brief persistence + history endpoint tests."""

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


def _seed_match_with_events(session, *, match_id: int):
    now = datetime.now(UTC)
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=now,
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id,
        league_external_id=203, season=2024,
        kickoff=now - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=0, tenant_id="t-default",
    ))
    for i in range(15):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(10 + i), period=1,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=1, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    session.commit()


def test_halftime_brief_persists_to_agent_outputs(session, client):
    _seed_match_with_events(session, match_id=4001)
    r = client.get("/admin/matches/4001/halftime-brief?my_team_id=11")
    assert r.status_code == 200
    # agent_outputs'a yazıldı mı
    rows = session.query(models.AgentOutput).filter_by(
        agent_name="halftime_analysis",
    ).all()
    assert len(rows) == 1
    assert rows[0].subject_id == 4001
    assert "team11" in rows[0].agent_version


def test_halftime_brief_persist_false_skips_save(session, client):
    _seed_match_with_events(session, match_id=4001)
    r = client.get("/admin/matches/4001/halftime-brief?my_team_id=11&persist=false")
    assert r.status_code == 200
    rows = session.query(models.AgentOutput).filter_by(
        agent_name="halftime_analysis",
    ).all()
    assert len(rows) == 0


def test_halftime_history_returns_saved_briefs(session, client):
    _seed_match_with_events(session, match_id=4001)
    client.get("/admin/matches/4001/halftime-brief?my_team_id=11")
    r = client.get("/admin/halftime-brief-history")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["match_id"] == 4001
    assert "team11" in body[0]["agent_version"]


def test_history_match_id_filter(session, client):
    _seed_match_with_events(session, match_id=4001)
    client.get("/admin/matches/4001/halftime-brief?my_team_id=11")
    r = client.get("/admin/halftime-brief-history?match_id=4001")
    assert len(r.json()) == 1
    r2 = client.get("/admin/halftime-brief-history?match_id=9999")
    assert len(r2.json()) == 0


def test_halftime_idempotent_update(session, client):
    """İki kere çağır: 1 satır kalmalı, updated_at yenilenmeli."""
    _seed_match_with_events(session, match_id=4001)
    client.get("/admin/matches/4001/halftime-brief?my_team_id=11")
    client.get("/admin/matches/4001/halftime-brief?my_team_id=11")
    rows = session.query(models.AgentOutput).filter_by(
        agent_name="halftime_analysis",
    ).all()
    assert len(rows) == 1  # idempotent
