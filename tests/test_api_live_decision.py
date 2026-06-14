"""Faz 6 live-decision endpoint tests."""
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


def _seed_match_events(session, match_id: int = 9300):
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
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    for i in range(30):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"p{i}",
            match_external_id=match_id, team_external_id=11,
            player_external_id=1, event_type="pass",
            minute=float(i * 2), period=1 if i * 2 < 45 else 2,
            start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
            outcome="completed", body_part=None, pattern="regular",
            possession_id=i, is_goal=None, key_pass=False,
            raw_json=None, created_at=now,
        ))
    session.commit()


def test_live_decision_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get("/admin/matches/99999/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 404


def test_live_decision_no_events(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=9300,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=1), status="FT",
        home_team_external_id=11, away_team_external_id=22,
        home_score=1, away_score=2, tenant_id="t-default",
    ))
    session.commit()
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=60")
    assert r.status_code == 200
    assert r.json()["events_loaded"] == 0


def test_live_decision_full_panel(session, client):
    _seed_match_events(session)
    r = client.get("/admin/matches/9300/live-decision?my_team_id=11&current_minute=70")
    assert r.status_code == 200
    body = r.json()
    assert "momentum" in body
    assert "sub_timing" in body
    assert "tactical_triggers" in body
    assert "risk_monitor" in body


def test_opponent_reaction_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/opponent-reaction?my_team_id=11&current_minute=70&momentum_score=-0.5",
        json={"opponent_subs": [{"position_in": "F", "minute": 65}]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opp_subs_detected"] == 1
    assert v["momentum_break_advice"] is not None


def test_live_risk_endpoint(session, client):
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": [
            {"player_id": 100, "yellow_card": True, "duel_count": 5},
            {"player_id": 200, "fatigue": 0.85},
        ]},
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert len(v["card_flags"]) == 1
    assert len(v["injury_flags"]) == 1
    # Geride (1-2) + 80. dk → tempoyu artır
    assert "tempoyu artır" in v["time_management"]


def test_live_risk_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/live-risk?my_team_id=11&current_minute=80",
        json={"player_states": []},
    )
    assert r.status_code == 404


def test_closing_strategy_endpoint(session, client):
    """Geride 1-2, 80. dk → tempo=agresif + risk=true."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/closing-strategy"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["score_state"] == "trailing"  # 1-2 → trailing
    assert v["closing_phase"] == "late"
    assert v["recipe"]["tempo"] == "agresif"
    assert v["risk_reward"]["take_risk"] is True


def test_closing_strategy_in_live_decision_panel(session, client):
    """live-decision birleşik panelinde closing_strategy var."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/live-decision"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 200
    body = r.json()
    assert "closing_strategy" in body
    cs = body["closing_strategy"]
    assert "recipe" in cs
    assert "risk_reward" in cs


def test_closing_strategy_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get(
        "/admin/matches/99999/closing-strategy"
        "?my_team_id=11&current_minute=80",
    )
    assert r.status_code == 404


def test_foul_pressure_endpoint(session, client):
    """Rakip ritim kırma + sarılı oyuncu → iki sinyal birden."""
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/foul-pressure"
        "?my_team_id=11&current_minute=75&total_yellows_match=7",
        json={
            "foul_events": [
                {"team_id": 22, "minute": 62.0},
                {"team_id": 22, "minute": 64.0},
                {"team_id": 22, "minute": 67.0},
                {"team_id": 22, "minute": 70.0},
                {"team_id": 22, "minute": 73.0},
                {"team_id": 11, "minute": 60.0, "player_id": 99},
                {"team_id": 11, "minute": 65.0, "player_id": 99},
                {"team_id": 11, "minute": 70.0, "player_id": 99},
            ],
            "player_yellow_cards": {"99": 1},
        },
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["tactical_fouling_alert"] is True
    assert v["referee_card_pressure"] == "high"
    assert len(v["player_flags"]) == 1
    assert v["player_flags"][0]["risk_level"] == "critical"


def test_foul_pressure_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.post(
        "/admin/matches/99999/foul-pressure"
        "?my_team_id=11&current_minute=75",
        json={"foul_events": []},
    )
    assert r.status_code == 404


def test_foul_pressure_empty_payload(session, client):
    """Payload yok + ingest edilmiş faul yok → normal advice + 0 faul."""
    _seed_match_events(session)
    r = client.post(
        "/admin/matches/9300/foul-pressure?my_team_id=11&current_minute=70",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["our_fouls_total"] == 0
    assert v["opp_fouls_total"] == 0
    assert "normal" in v["tactical_advice"].lower()


def test_foul_pressure_reads_ingested_fouls(session, client):
    """Payload boş ama DB'de foul EventRow var → engine onları okur."""
    _seed_match_events(session)
    # 5 rakip faul + 1 sarı bizden
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"foul-opp-{i}",
            match_external_id=9300, team_external_id=22,
            player_external_id=100 + i, event_type="foul",
            minute=float(62 + i), period=2,
            start_x=60.0, start_y=40.0, end_x=None, end_y=None,
            outcome="foul", body_part=None, pattern=None,
            possession_id=None, is_goal=None, key_pass=None,
            raw_json=None, created_at=now,
        ))
    session.add(models.EventRow(
        sport=football.SPORT_NAME, tenant_id="t-default",
        source="statsbomb_open", source_event_id="foul-our-1",
        match_external_id=9300, team_external_id=11,
        player_external_id=200, event_type="foul",
        minute=60.0, period=2,
        start_x=60.0, start_y=40.0, end_x=None, end_y=None,
        outcome="yellow", body_part=None, pattern=None,
        possession_id=None, is_goal=None, key_pass=None,
        raw_json=None, created_at=now,
    ))
    session.commit()
    r = client.post(
        "/admin/matches/9300/foul-pressure?my_team_id=11&current_minute=75",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["opp_fouls_total"] == 5
    assert v["our_fouls_total"] == 1
    assert v["tactical_fouling_alert"] is True
    # 1 sarı maçta → low (eşik moderate=4)
    assert v["referee_card_pressure"] == "low"


def test_live_decision_panel_includes_foul_pressure_when_ingested(session, client):
    """Live decision panel ingest'lenmiş foul'ları otomatik içerir."""
    _seed_match_events(session)
    # 5 rakip foul ekle
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    for i in range(5):
        session.add(models.EventRow(
            sport=football.SPORT_NAME, tenant_id="t-default",
            source="statsbomb_open", source_event_id=f"foul-{i}",
            match_external_id=9300, team_external_id=22,
            player_external_id=100, event_type="foul",
            minute=float(62 + i), period=2,
            start_x=60.0, start_y=40.0, end_x=None, end_y=None,
            outcome="foul", body_part=None, pattern=None,
            possession_id=None, is_goal=None, key_pass=None,
            raw_json=None, created_at=now,
        ))
    session.commit()
    r = client.get(
        "/admin/matches/9300/live-decision"
        "?my_team_id=11&current_minute=75",
    )
    assert r.status_code == 200
    body = r.json()
    assert "foul_pressure" in body
    assert body["foul_pressure"]["opp_fouls_total"] == 5


def test_star_feed_endpoint(session, client):
    """Seed match'te tek oyuncu (id=1) tüm pasları atıyor → well-fed."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/star-feed"
        "?my_team_id=11&star_player_id=1&current_minute=70&window_min=15",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    # Seed'te tüm paslar player_id=1 → yıldız = %100
    assert v["pass_share_pct"] == 100.0
    assert v["involvement_state"] == "well-fed"


def test_star_feed_starved_when_other_player(session, client):
    """Yıldız = farklı oyuncu → starved."""
    _seed_match_events(session)
    r = client.get(
        "/admin/matches/9300/star-feed"
        "?my_team_id=11&star_player_id=999&current_minute=70&window_min=15",
    )
    assert r.status_code == 200
    v = r.json()["value"]
    assert v["involvement_state"] == "starved"
    assert "HİÇ pas" in v["tactical_advice"]


def test_star_feed_404(session, client):
    session.add(models.Tenant(
        id="t-default", slug="t-default", name="X",
        settings_json="{}", active=True, created_at=datetime.now(UTC),
    ))
    session.commit()
    r = client.get(
        "/admin/matches/99999/star-feed"
        "?my_team_id=11&star_player_id=1&current_minute=70",
    )
    assert r.status_code == 404
