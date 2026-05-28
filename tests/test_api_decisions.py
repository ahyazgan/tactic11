"""Decision audit log endpoint tests."""

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
    # Tenant context — auth bypass'lı test client için
    session.info["tenant_id"] = "t-default"
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_match(session, match_id: int = 8001):
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
        home_score=2, away_score=1, tenant_id="t-default",
    ))
    session.commit()


def test_create_substitution_decision(session, client):
    _seed_match(session)
    r = client.post("/admin/matches/8001/decisions", json={
        "team_external_id": 11,
        "minute": 65.0,
        "decision_type": "substitution",
        "subject_player_external_id": 100,
        "related_player_external_id": 200,
        "notes": "Yorgun, hücum oyuncusu lazım",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["decision_type"] == "substitution"
    assert body["minute"] == 65.0
    assert body["id"] > 0


def test_create_decision_validates_required(session, client):
    _seed_match(session)
    r = client.post("/admin/matches/8001/decisions", json={
        "team_external_id": 11,
        "minute": 70.0,
        # decision_type yok
    })
    assert r.status_code == 400
    assert "eksik alan" in r.json()["detail"]


def test_create_decision_validates_type(session, client):
    _seed_match(session)
    r = client.post("/admin/matches/8001/decisions", json={
        "team_external_id": 11,
        "minute": 70.0,
        "decision_type": "weird_type",
    })
    assert r.status_code == 400


def test_list_decisions_ordered_by_minute(session, client):
    _seed_match(session)
    for m, t in [(80.0, "tactical_instruction"),
                  (65.0, "substitution"),
                  (45.0, "formation_change")]:
        client.post("/admin/matches/8001/decisions", json={
            "team_external_id": 11,
            "minute": m,
            "decision_type": t,
        })
    r = client.get("/admin/matches/8001/decisions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    # Minute ascending
    minutes = [d["minute"] for d in body]
    assert minutes == sorted(minutes)


def test_decisions_learning_no_events(session, client):
    """Event ingest yoksa: events_loaded=0 + note."""
    _seed_match(session)
    r = client.get("/admin/matches/8001/decisions/learning")
    body = r.json()
    assert body["events_loaded"] == 0
    assert "Event ingest yapılmamış" in body["note"]


def test_decisions_learning_match_not_found(session, client):
    r = client.get("/admin/matches/99999/decisions/learning")
    assert r.status_code == 404


def test_decisions_learning_with_events_and_decision(session, client):
    """1 decision + before/after event'ler → impact analizi."""
    _seed_match(session)
    # 60. dk öncesi 5 pas + sonrası 5 pas
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"pre{i}",
            match_external_id=8001, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(50 + i), period=2,
            start_x=50.0, start_y=50.0, end_x=60.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"post{i}",
            match_external_id=8001, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(62 + i), period=2,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=10 + i, is_goal=None, key_pass=False,
            raw_json=None, created_at=datetime.now(UTC),
        ))
    session.commit()
    client.post("/admin/matches/8001/decisions", json={
        "team_external_id": 11,
        "minute": 60.0,
        "decision_type": "substitution",
        "subject_player_external_id": 100,
        "related_player_external_id": 200,
    })
    r = client.get("/admin/matches/8001/decisions/learning")
    body = r.json()
    assert body["decisions_analyzed"] >= 1
    assert "impacts" in body
    impact = body["impacts"][0]
    assert "xt_delta" in impact
    assert "verdict" in impact
    assert impact["verdict"] in ("positive", "negative", "neutral")
