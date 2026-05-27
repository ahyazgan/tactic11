"""Engine result cache (snapshot-keyed) için testler.

Hem helper'ı doğrudan, hem de /matches/{id}/predict endpoint'inde
entegrasyonu test ediyoruz.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.data.cache import engine_cached
from app.db import models
from app.db.session import get_session
from app.snapshot import save_snapshot
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


def _seed_for_predict(session, base: datetime):
    rows = [
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
        models.Match(
            sport=football.SPORT_NAME, external_id=3, league_external_id=203, season=2024,
            kickoff=base - timedelta(days=5), status="FT",
            home_team_external_id=607, away_team_external_id=611, home_score=0, away_score=0,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203, season=2024,
            kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607, home_score=None, away_score=None,
        ),
    ]
    session.add_all(rows + [
        models.Team(sport=football.SPORT_NAME, external_id=611, name="Galatasaray", country="Turkey"),
        models.Team(sport=football.SPORT_NAME, external_id=607, name="Fenerbahce", country="Turkey"),
        models.Team(sport=football.SPORT_NAME, external_id=614, name="Besiktas", country="Turkey"),
    ])
    session.flush()


def test_engine_cached_bypass_when_no_snapshot(session):
    """Snapshot yoksa cache atlanır, doğrudan compute çağrılır."""
    calls = []

    def _compute():
        calls.append(1)
        return {"value": 42}

    r1, hit1 = engine_cached(
        session, sport=football.SPORT_NAME,
        key_parts=("test", "x"), compute_fn=_compute,
    )
    assert r1 == {"value": 42}
    assert hit1 is False
    # İkinci çağrı da bypass (snapshot hâlâ yok)
    r2, hit2 = engine_cached(
        session, sport=football.SPORT_NAME,
        key_parts=("test", "x"), compute_fn=_compute,
    )
    assert hit2 is False
    assert len(calls) == 2  # her ikisi de compute çalıştırdı


def test_engine_cached_hit_after_first_miss(session):
    """Snapshot varsa ilk çağrı miss, ikinci aynı parametrelerle hit."""
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()
    calls = []

    def _compute():
        calls.append(1)
        return {"value": 42}

    r1, hit1 = engine_cached(
        session, sport=football.SPORT_NAME,
        key_parts=("test", "x"), compute_fn=_compute,
    )
    assert hit1 is False
    assert len(calls) == 1
    r2, hit2 = engine_cached(
        session, sport=football.SPORT_NAME,
        key_parts=("test", "x"), compute_fn=_compute,
    )
    assert hit2 is True
    assert r2 == r1
    assert len(calls) == 1  # ikinci kez compute çağrılmadı


def test_engine_cached_invalidates_on_new_snapshot(session):
    """Yeni snapshot → cache key prefix değişir → eski satırlar erişilmez."""
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()
    calls = []

    def _compute():
        calls.append(1)
        return {"v": len(calls)}  # her çağrıda farklı

    # İlk snapshot altında 2 çağrı: miss + hit
    r1, _ = engine_cached(session, sport=football.SPORT_NAME, key_parts=("x",), compute_fn=_compute)
    r2, hit2 = engine_cached(session, sport=football.SPORT_NAME, key_parts=("x",), compute_fn=_compute)
    assert hit2 is True
    assert r2 == r1

    # Yeni snapshot oluştur → key prefix değişir
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()
    r3, hit3 = engine_cached(session, sport=football.SPORT_NAME, key_parts=("x",), compute_fn=_compute)
    assert hit3 is False  # yeni snapshot, yeni key, miss
    assert r3 != r1  # compute_fn yeni değer döndü
    assert len(calls) == 2  # ilk + yeni snapshot'taki compute


def test_engine_cached_different_keys_are_independent(session):
    """Farklı key_parts → ayrı cache satırları."""
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()
    calls_a, calls_b = [], []

    def _a():
        calls_a.append(1)
        return {"k": "a"}

    def _b():
        calls_b.append(1)
        return {"k": "b"}

    engine_cached(session, sport=football.SPORT_NAME, key_parts=("a",), compute_fn=_a)
    engine_cached(session, sport=football.SPORT_NAME, key_parts=("b",), compute_fn=_b)
    engine_cached(session, sport=football.SPORT_NAME, key_parts=("a",), compute_fn=_a)
    # İkinci 'a' hit; 'b' tek miss
    assert len(calls_a) == 1
    assert len(calls_b) == 1


def test_predict_endpoint_cache_returns_identical_response(session, client):
    """İki ardışık çağrı bayt düzeyinde aynı yanıtı vermeli (snapshot varsa)."""
    _seed_for_predict(session, datetime.now(UTC))
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()

    r1 = client.get("/matches/99/predict")
    r2 = client.get("/matches/99/predict")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_predict_endpoint_cache_skipped_for_explain(session, client):
    """explain=true Claude'a gider; cache atlanır ama 200 dönmeli."""
    _seed_for_predict(session, datetime.now(UTC))
    save_snapshot(session, sport=football.SPORT_NAME, league_id=203, season=2024)
    session.commit()

    r = client.get("/matches/99/predict?explain=true")
    assert r.status_code == 200
    body = r.json()
    assert "explanation" in body
    # Engine sonucu hâlâ payload'da
    assert body["audit"]["engine"] == "engine.predict"
