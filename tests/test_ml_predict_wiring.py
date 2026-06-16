"""ML predict v3 production wiring — /admin/ml-model-status + /predict?use_ml=true (PR I1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.data.cache.store import cache_set
from app.db import models
from app.db.session import get_session
from app.engine.predict_ml import CACHE_KEY, CACHE_SOURCE
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


def _seed_match_with_history(session, base: datetime, match_id: int = 99):
    rows = [
        models.Match(
            sport=football.SPORT_NAME, external_id=1, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=607,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=2, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=614, away_team_external_id=611,
            home_score=1, away_score=3,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=match_id, league_external_id=203,
            season=2024, kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
        ),
    ]
    session.add_all(rows)
    session.flush()


def _populate_ml_cache(session, *, best_rho: float, sample_count: int = 50):
    cache_set(
        session, source=CACHE_SOURCE, key=CACHE_KEY,
        value={
            "best_rho": best_rho,
            "best_log_loss": 0.55,
            "sample_count": sample_count,
            "rho_grid": [-0.2, -0.18, -0.16, -0.14, -0.12, -0.10],
            "log_loss_per_rho": {"-0.2": 0.6, "-0.12": 0.55, "0.0": 0.7},
        },
        ttl_seconds=30 * 86_400,
    )
    session.flush()


# ---- /admin/ml-model-status ----------------------------------------------


def test_ml_model_status_untrained_when_no_cache(client):
    r = client.get("/admin/ml-model-status")
    assert r.status_code == 200
    assert r.json() == {"status": "untrained"}


def test_ml_model_status_fresh_when_cache_populated(session, client):
    _populate_ml_cache(session, best_rho=-0.14, sample_count=42)
    r = client.get("/admin/ml-model-status")
    body = r.json()
    assert body["status"] == "fresh"
    assert body["best_rho"] == -0.14
    assert body["sample_count"] == 42
    assert body["best_log_loss"] == 0.55
    assert "rho_grid" in body and "log_loss_per_rho" in body


def test_ml_model_status_stale_when_cache_expired(session, client):
    # Süresi geçmiş cache satırı manuel ekle
    now = datetime.now(UTC)
    session.add(models.CacheEntry(
        source=CACHE_SOURCE, key=CACHE_KEY,
        value='{"best_rho": -0.14, "sample_count": 42}',
        expires_at=now - timedelta(days=1),  # geçmişte
    ))
    session.flush()
    r = client.get("/admin/ml-model-status")
    body = r.json()
    assert body["status"] == "stale"
    assert "expires_at" in body


# ---- /matches/{id}/predict?use_ml=true -----------------------------------


def test_predict_use_ml_false_default_behavior(session, client):
    """Default use_ml=false → audit.inputs.ml_status alanı yok."""
    _seed_match_with_history(session, datetime.now(UTC))
    r = client.get("/matches/99/predict")
    body = r.json()
    assert "ml_status" not in body["audit"]["inputs"]


def test_predict_use_ml_true_untrained_falls_back(session, client):
    """use_ml=true ama cache yok → default ρ, ml_status=untrained."""
    _seed_match_with_history(session, datetime.now(UTC))
    r = client.get("/matches/99/predict?use_ml=true")
    body = r.json()
    assert body["audit"]["inputs"]["ml_status"] == "untrained"
    # rho default değer (compute_predict'in default'u -0.12)
    assert body["audit"]["inputs"]["rho"] == pytest.approx(-0.12)


def test_predict_use_ml_true_fresh_uses_learned_rho(session, client):
    """Cache populate'lı → learned ρ kullanılır."""
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_ml_cache(session, best_rho=-0.06)
    r = client.get("/matches/99/predict?use_ml=true")
    body = r.json()
    assert body["audit"]["inputs"]["ml_status"] == "fresh"
    assert body["audit"]["inputs"]["rho"] == pytest.approx(-0.06)
    # rho_used da PredictReport'ta görünür
    assert body["value"]["rho_used"] == pytest.approx(-0.06)


def test_predict_use_ml_true_stale_falls_back(session, client):
    """Cache expired → ml_status=stale + default ρ fallback."""
    _seed_match_with_history(session, datetime.now(UTC))
    now = datetime.now(UTC)
    session.add(models.CacheEntry(
        source=CACHE_SOURCE, key=CACHE_KEY,
        value='{"best_rho": -0.06}',
        expires_at=now - timedelta(days=1),
    ))
    session.flush()
    r = client.get("/matches/99/predict?use_ml=true")
    body = r.json()
    assert body["audit"]["inputs"]["ml_status"] == "stale"
    assert body["audit"]["inputs"]["rho"] == pytest.approx(-0.12)  # default


def test_predict_use_ml_separate_cache_from_default(session, client):
    """use_ml=true ve use_ml=false ayrı engine_cached entries — sırayla
    çağrılınca iki ayrı prediction satırı görünür (cache key farklı)."""
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_ml_cache(session, best_rho=-0.06)
    # use_ml=false (default ρ)
    r1 = client.get("/matches/99/predict")
    # use_ml=true (learned ρ)
    r2 = client.get("/matches/99/predict?use_ml=true")
    assert r1.json()["audit"]["inputs"]["rho"] == pytest.approx(-0.12)
    assert r2.json()["audit"]["inputs"]["rho"] == pytest.approx(-0.06)
