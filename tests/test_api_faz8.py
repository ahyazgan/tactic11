"""Faz 8 endpoint tests — live-decision context + decision outcome/feedback."""
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
    session.info["tenant_id"] = "t-default"

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_match_events(session, match_id: int = 9500):
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
        home_score=0, away_score=0, tenant_id="t-default",
    ))
    for i in range(40):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 1.6), period=1 if i * 1.6 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=75.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()


def test_live_decision_has_context(session, client):
    """Orkestra şefi: live-decision artık tek 'context' kararı döndürür."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9500/live-decision?my_team_id=11&current_minute=70"
    )
    assert r.status_code == 200
    body = r.json()
    assert "context" in body
    assert "error" not in body["context"]
    assert "one_liner" in body["context"]
    assert "match_memory" in body


def test_decision_outcome_and_feedback(session, client):
    """#4 audit trail: karar kaydet → sonuç işle → feedback hit-rate."""
    _seed_match_events(session)
    # karar kaydet (öneri kaynaklı, güvenli)
    r = client.post("/admin/matches/9500/decisions", json={
        "team_external_id": 11, "minute": 67.0,
        "decision_type": "substitution",
        "subject_player_external_id": 100,
        "recommended": True, "confidence": 0.72,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["recommended"] is True
    assert body["outcome"] == "pending"
    decision_id = body["id"]

    # sonucu işle
    r2 = client.post(f"/admin/decisions/{decision_id}/outcome", json={
        "outcome": "positive", "outcome_value": 0.8,
    })
    assert r2.status_code == 200
    assert r2.json()["outcome"] == "positive"

    # feedback hit-rate
    r3 = client.get("/admin/teams/11/decisions/feedback")
    assert r3.status_code == 200
    fb = r3.json()
    assert fb["evaluated"] == 1
    assert fb["by_decision_type"]["substitution"]["hit_rate"] == 1.0


def test_outcome_404_for_missing_decision(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post("/admin/decisions/99999/outcome",
                    json={"outcome": "positive"})
    assert r.status_code == 404


def test_outcome_validates_value(session, client):
    _seed_match_events(session)
    r = client.post("/admin/matches/9500/decisions", json={
        "team_external_id": 11, "minute": 70.0,
        "decision_type": "tactical_instruction",
    })
    did = r.json()["id"]
    bad = client.post(f"/admin/decisions/{did}/outcome",
                      json={"outcome": "harika"})
    assert bad.status_code == 400
