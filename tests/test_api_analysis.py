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


def test_team_schedule_counts_upcoming(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/schedule?horizon_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.schedule"
    assert body["value"]["upcoming_count"] == 1  # sadece NS match 99
    assert body["value"]["matches_next_7d"] == 1
    # match 99 ~2 gün sonra → days_until_next_match küçük pozitif
    assert 0 < body["value"]["days_until_next_match"] < 7


def test_team_schedule_404_for_unknown_team(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/999999/schedule")
    assert r.status_code == 404


def test_matchup_returns_engine_value(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matchup/611/607?last_n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.matchup"
    assert body["value"]["home_team_id"] == 611
    assert body["value"]["away_team_id"] == 607
    # Galatasaray (611) form daha güçlü → ppg delta pozitif
    assert body["value"]["form_delta_ppg"] > 0


def test_matchup_rejects_self_pair(session, client):
    r = client.get("/matchup/611/611")
    assert r.status_code == 400


def test_matchup_404_when_team_has_no_matches(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matchup/611/999999")
    assert r.status_code == 404


def test_match_predict_returns_poisson(session, client):
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/predict")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.predict"
    v = body["value"]
    # Olasılıklar ~1'e toplanır (max_goals=10 grid kuyruk toleransı)
    total = v["prob_home_win"] + v["prob_draw"] + v["prob_away_win"]
    assert abs(total - 1.0) < 0.01
    # Galatasaray form daha güçlü → ev galibiyeti olasılığı en yüksek
    assert v["prob_home_win"] > v["prob_away_win"]
    # Form sample küçük (2) → low_confidence flag
    assert v["low_confidence"] is True
    assert v["sample_size"] == 2


def test_match_predict_404_for_unknown_match(session, client):
    r = client.get("/matches/123456789/predict")
    assert r.status_code == 404


def test_match_predict_excludes_match_itself(session, client):
    """Form, maçın kickoff'undan önceki maçlardan; match 99 (NS) dahil olmamalı."""
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/predict")
    assert r.status_code == 200
    body = r.json()
    # 611 için 3 geçmiş maç, 607 için 2 → sample_size = min(3,2) = 2
    assert body["value"]["sample_size"] == 2


def test_team_fixture_difficulty_uses_opponent_ratings(session, client):
    """Match 99 (Gala home vs Fener, NS, 2 gün sonra) → tek upcoming rakip 607."""
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/teams/611/fixture-difficulty?horizon_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["audit"]["engine"] == "engine.fixture_difficulty"
    v = body["value"]
    # 607'nin geçmiş maçları var → rating bilinir
    assert v["matches_considered"] == 1
    assert v["matches_unknown_opponent"] == 0
    assert v["hardest_opponent_id"] == 607
    assert v["home_match_count"] == 1
    assert v["away_match_count"] == 0


def test_team_fixture_difficulty_404_for_unknown_team(session, client):
    r = client.get("/teams/999999/fixture-difficulty")
    assert r.status_code == 404


def test_team_fixture_difficulty_empty_horizon(session, client):
    """Çok kısa ufukta upcoming kalmıyor → rapor boş ama 200."""
    _seed_matches(session, datetime.now(UTC))
    # Match 99 ~2 gün sonra; horizon_days=1 → ufuk dışı
    r = client.get("/teams/611/fixture-difficulty?horizon_days=1")
    assert r.status_code == 200
    body = r.json()
    assert body["value"]["matches_considered"] == 0
    assert body["value"]["hardest_opponent_id"] is None
