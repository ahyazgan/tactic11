"""API analiz uçları için TestClient testleri.

In-memory SQLite + override get_session ile gerçek DB gerektirmeden çalışır.
"""

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


def _seed_matches(session, base: datetime):
    rows = [
        # Galatasaray (611) maçları
        models.Match(
            sport=football.SPORT_NAME, external_id=1, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=607, home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=2, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=614, away_team_external_id=611, home_score=1, away_score=3,
        ),
        # Fenerbahce (607) — Galatasaray'la başka bir maç
        models.Match(
            sport=football.SPORT_NAME, external_id=3, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=5), status="FT",
            home_team_external_id=607, away_team_external_id=611, home_score=0, away_score=0,
        ),
        # Henüz oynanmamış maç — preview için hedef
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203, season=2024,
            kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607, home_score=None, away_score=None,
        ),
    ]
    # League + Team kayıtları (teams_in_league için)
    session.add_all(rows + [
        models.League(sport=football.SPORT_NAME, external_id=203, name="Süper Lig", season=2024),
        models.Team(sport=football.SPORT_NAME, external_id=611, name="Galatasaray", country="Turkey"),
        models.Team(sport=football.SPORT_NAME, external_id=607, name="Fenerbahce", country="Turkey"),
        models.Team(sport=football.SPORT_NAME, external_id=614, name="Besiktas", country="Turkey"),
    ])
    session.flush()


def test_team_form_returns_engine_value_and_audit(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/form?last_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["value"]["matches_played"] == 3
    assert body["value"]["wins"] == 2
    assert body["value"]["draws"] == 1
    assert body["audit"]["engine"] == "engine.form"
    assert body["audit"]["subject_id"] == 611


def test_team_rating_endpoint(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/rating?last_n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.rating"
    assert body["value"]["matches_considered"] == 3


def test_head_to_head_endpoint(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/vs/607")
    assert r.status_code == 200
    body = r.json()
    # 3 maç oynanmış değil; H2H bitmiş 2 + 1 berabere = 3
    assert body["value"]["matches_played"] == 2  # finished arasından
    # 1 (Gala home 2-1 W) + 1 (Fener home 0-0 D) = 2 finished
    assert body["audit"]["engine"] == "engine.opponent"


def test_head_to_head_rejects_self_pair(session, client):
    r = client.get("/teams/611/vs/611")
    assert r.status_code == 400


def test_match_preview_excludes_match_itself_from_form(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["match"]["external_id"] == 99
    # form sadece kickoff'tan ÖNCEKİ maçlar; NS olan 99 dahil edilmemeli
    assert body["home_form"]["value"]["matches_played"] == 3
    assert body["away_form"]["value"]["matches_played"] == 2
    # H2H Galatasaray vs Fenerbahce: 1 finished (1234001 değil burada id=1 ve id=3)
    assert body["head_to_head"]["value"]["matches_played"] == 2


def test_match_preview_404_for_unknown(session, client):
    r = client.get("/matches/123456789/preview")
    assert r.status_code == 404


def test_explain_flag_returns_stub_when_no_api_key(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/form?explain=true")
    assert r.status_code == 200
    body = r.json()
    assert "explanation" in body
    # Anahtar yok → stub
    assert "stub" in body["explanation"].lower()


def test_match_preview_explain_returns_stub_when_no_api_key(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/preview?explain=true")
    assert r.status_code == 200
    body = r.json()
    assert "explanation" in body
    assert "stub:match_preview" in body["explanation"]
    assert "611" in body["explanation"] and "607" in body["explanation"]
    # Engine sonuçları hâlâ payload'da
    assert "home_form" in body and "away_form" in body and "head_to_head" in body
