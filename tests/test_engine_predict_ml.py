"""engine.predict_ml — train + compute (PR H1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db import models
from app.engine.predict_ml import (
    RHO_GRID,
    NotEnoughTrainingData,
    compute_ml_predict,
    train_best_rho,
)
from app.scheduler.registry import get


def _seed_predict_with_outcome(
    session, *, match_id: int, lam_home: float, lam_away: float, actual: str
) -> None:
    """Predictions tablosuna engine.predict-formatlı bir satır ekle."""
    now = datetime.now(UTC)
    session.add(models.Prediction(
        sport="football",
        match_external_id=match_id,
        engine="engine.predict",
        engine_version="2",
        params_hash=f"h{match_id}",
        params_json="{}",
        predicted_value_json=json.dumps({
            "expected_home_goals": lam_home,
            "expected_away_goals": lam_away,
            "prob_home_win": 0.4,
            "prob_draw": 0.3,
            "prob_away_win": 0.3,
        }),
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=10),
        actual_home_score=0,
        actual_away_score=0,
        actual_outcome=actual,
        reconciled_at=now,
    ))
    session.flush()


def test_train_not_enough_data_raises(session):
    with pytest.raises(NotEnoughTrainingData):
        train_best_rho(session, min_samples=20)


def test_train_with_few_samples_explicit_min_ok(session):
    """min_samples=2 ile 2 sample → train çalışır."""
    _seed_predict_with_outcome(session, match_id=1, lam_home=2.0, lam_away=0.5, actual="home")
    _seed_predict_with_outcome(session, match_id=2, lam_home=0.5, lam_away=2.0, actual="away")
    report = train_best_rho(session, min_samples=2)
    assert report.sample_count == 2
    assert report.best_rho is not None
    assert report.best_rho in RHO_GRID
    # log_loss_per_rho her ρ için bir değer içeriyor
    assert len(report.log_loss_per_rho) == len(RHO_GRID)


def test_train_skips_predictions_without_actual(session):
    """actual_outcome NULL olan satırlar training'e dahil değil."""
    _seed_predict_with_outcome(session, match_id=1, lam_home=2.0, lam_away=0.5, actual="home")
    # Bir tane reconcile edilmemiş (actual=None) ekle — direct
    now = datetime.now(UTC)
    session.add(models.Prediction(
        sport="football", match_external_id=2,
        engine="engine.predict", engine_version="2",
        params_hash="h2", params_json="{}",
        predicted_value_json=json.dumps({
            "expected_home_goals": 1.0, "expected_away_goals": 1.0,
        }),
        created_at=now, updated_at=now,
        actual_home_score=None, actual_away_score=None,
        actual_outcome=None, reconciled_at=None,
    ))
    session.flush()
    # min=1 ile train edebiliriz ama sadece 1 sample sayılmalı
    report = train_best_rho(session, min_samples=1)
    assert report.sample_count == 1


def test_train_skips_other_engines(session):
    """engine adı 'engine.predict' olmayan kayıtlar atlanır (ml dahil)."""
    _seed_predict_with_outcome(session, match_id=1, lam_home=2.0, lam_away=0.5, actual="home")
    now = datetime.now(UTC)
    session.add(models.Prediction(
        sport="football", match_external_id=2,
        engine="engine.predict_ml", engine_version="1",  # farklı engine
        params_hash="hml", params_json="{}",
        predicted_value_json=json.dumps({
            "expected_home_goals": 1.0, "expected_away_goals": 1.0,
        }),
        created_at=now, updated_at=now,
        actual_outcome="home", reconciled_at=now,
    ))
    session.flush()
    report = train_best_rho(session, min_samples=1)
    # Sadece engine.predict satırı sayıldı
    assert report.sample_count == 1


def test_compute_ml_predict_uses_learned_rho(session):
    """compute_ml_predict(learned_rho=0) saf Poisson'la aynı sonucu vermeli."""
    # Test için minimal form üret
    from app.domain import Match
    from app.engine.form import compute_form
    from app.engine.predict import compute_predict
    from app.sports import football
    matches = [
        Match(
            sport=football.SPORT_NAME, external_id=i,
            league_external_id=203, season=2024,
            kickoff=datetime.now(UTC) - timedelta(days=i + 1),
            status="FT",
            home_team_external_id=611, away_team_external_id=999 - i,
            home_score=2, away_score=0,
        )
        for i in range(5)
    ]
    home_form = compute_form(611, matches, last_n=5).value
    away_form = compute_form(607, matches, last_n=5).value  # 0 maç

    ml_result = compute_ml_predict(
        home_form, away_form,
        home_team_id=611, away_team_id=607, learned_rho=0.0,
    )
    poisson_result = compute_predict(
        home_form, away_form,
        home_team_id=611, away_team_id=607, rho=0.0,
    )
    # learned_rho=0 → identical to pure Poisson
    assert ml_result.value.prob_home_win == poisson_result.value.prob_home_win
    assert ml_result.value.rho_used == 0.0


def test_train_predict_ml_job_registered():
    spec = get("train_predict_ml")
    assert spec.name == "train_predict_ml"
    assert callable(spec.handler)
