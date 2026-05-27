"""Prediction storage (PR B1) — save_prediction idempotency + endpoint integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.data.predictions import save_prediction
from app.data.predictions.store import _params_hash
from app.db import models
from app.db.session import get_session
from app.engine.form import compute_form
from app.engine.predict import compute_predict
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
    session.add_all([
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
            sport=football.SPORT_NAME, external_id=99, league_external_id=203, season=2024,
            kickoff=base + timedelta(days=2), status="NS",
            home_team_external_id=611, away_team_external_id=607, home_score=None, away_score=None,
        ),
    ])
    session.flush()


def test_params_hash_deterministic_and_order_independent():
    h1 = _params_hash({"last_n": 5, "rho": -0.12})
    h2 = _params_hash({"rho": -0.12, "last_n": 5})  # farklı sıra
    assert h1 == h2
    assert len(h1) == 32


def test_save_prediction_creates_row(session):
    _seed_matches(session, datetime.now(UTC))
    # 99 maçı için form çağırarak gerçek bir EngineResult üret
    matches_611 = list(session.execute(
        select(models.Match).where(
            models.Match.home_team_external_id == 611
        )
    ).scalars())
    matches_607 = list(session.execute(
        select(models.Match).where(
            models.Match.away_team_external_id == 607
        )
    ).scalars())
    # Quick predict
    home_form = compute_form(611, matches_611, last_n=5).value
    away_form = compute_form(607, matches_607, last_n=5).value
    result = compute_predict(home_form, away_form, home_team_id=611, away_team_id=607)

    row = save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=99, result=result, params={"last_n": 5},
    )
    assert row.id is not None
    assert row.engine == "engine.predict"
    assert row.engine_version == "2"
    assert row.match_external_id == 99
    assert row.actual_outcome is None  # reconcile job henüz çalışmadı


def test_save_prediction_is_idempotent(session):
    _seed_matches(session, datetime.now(UTC))
    matches = list(session.execute(select(models.Match)).scalars())
    f611 = compute_form(611, matches, last_n=5).value
    f607 = compute_form(607, matches, last_n=5).value
    r = compute_predict(f611, f607, home_team_id=611, away_team_id=607)

    row1 = save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=99, result=r, params={"last_n": 5},
    )
    row2 = save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=99, result=r, params={"last_n": 5},
    )
    assert row1.id == row2.id  # aynı satır (upsert)
    rows = session.execute(select(models.Prediction)).scalars().all()
    assert len(rows) == 1


def test_save_prediction_different_params_different_row(session):
    _seed_matches(session, datetime.now(UTC))
    matches = list(session.execute(select(models.Match)).scalars())
    f611 = compute_form(611, matches, last_n=5).value
    f607 = compute_form(607, matches, last_n=5).value
    r = compute_predict(f611, f607, home_team_id=611, away_team_id=607)

    save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=99, result=r, params={"last_n": 5},
    )
    save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=99, result=r, params={"last_n": 10},  # farklı params
    )
    rows = session.execute(select(models.Prediction)).scalars().all()
    assert len(rows) == 2


def test_predict_endpoint_saves_prediction(session, client):
    """GET /matches/99/predict → predictions satırı oluşur."""
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/predict")
    assert r.status_code == 200
    # DB'de satır var
    rows = session.execute(select(models.Prediction)).scalars().all()
    assert len(rows) == 1
    assert rows[0].match_external_id == 99
    assert rows[0].engine == "engine.predict"


def test_predict_endpoint_idempotent_calls(session, client):
    """İki ardışık /predict çağrısı → 1 satır (cache miss üzerinde idempotent)."""
    _seed_matches(session, datetime.now(UTC))
    client.get("/matches/99/predict")
    client.get("/matches/99/predict")
    rows = session.execute(select(models.Prediction)).scalars().all()
    assert len(rows) == 1


def test_predict_endpoint_explain_also_saves(session, client):
    """explain=true cache atlasa da prediction saklanmalı."""
    _seed_matches(session, datetime.now(UTC))
    r = client.get("/matches/99/predict?explain=true")
    assert r.status_code == 200
    rows = session.execute(select(models.Prediction)).scalars().all()
    assert len(rows) == 1
