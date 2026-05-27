"""Reconcile job — bitmiş maçların actual_* alanlarını dolduran scheduler işi."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data.predictions import reconcile_pending_predictions, save_prediction
from app.db import models
from app.engine.form import compute_form
from app.engine.predict import compute_predict
from app.scheduler.registry import get
from app.sports import football


def _seed_match_and_prediction(
    session, match_id: int, *, status: str, home_score: int | None, away_score: int | None
):
    base = datetime.now(UTC)
    # match
    session.add(models.Match(
        sport=football.SPORT_NAME, external_id=match_id, league_external_id=203,
        season=2024, kickoff=base - timedelta(days=2),
        status=status, home_team_external_id=611, away_team_external_id=607,
        home_score=home_score, away_score=away_score,
    ))
    # Tahmin için pre-game forma ihtiyaç var — basit form üret
    past = models.Match(
        sport=football.SPORT_NAME, external_id=match_id + 1000, league_external_id=203,
        season=2024, kickoff=base - timedelta(days=20),
        status="FT", home_team_external_id=611, away_team_external_id=998,
        home_score=2, away_score=1,
    )
    session.add(past)
    session.flush()
    matches = [past]
    f611 = compute_form(611, matches, last_n=5).value
    f607 = compute_form(607, matches, last_n=5).value
    r = compute_predict(f611, f607, home_team_id=611, away_team_id=607)
    save_prediction(
        session, sport=football.SPORT_NAME,
        match_external_id=match_id, result=r, params={"last_n": 5},
    )
    session.flush()


def test_reconcile_fills_actual_for_finished_home_win(session):
    _seed_match_and_prediction(session, 1, status="FT", home_score=3, away_score=1)
    r = reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    assert r.scanned == 1
    assert r.updated == 1

    pred = session.execute(
        models.Prediction.__table__.select().where(
            models.Prediction.match_external_id == 1
        )
    ).fetchone()
    assert pred.actual_home_score == 3
    assert pred.actual_away_score == 1
    assert pred.actual_outcome == "home"
    assert pred.reconciled_at is not None


def test_reconcile_outcome_away_win(session):
    _seed_match_and_prediction(session, 2, status="FT", home_score=0, away_score=2)
    reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    pred = session.execute(
        models.Prediction.__table__.select().where(
            models.Prediction.match_external_id == 2
        )
    ).fetchone()
    assert pred.actual_outcome == "away"


def test_reconcile_outcome_draw(session):
    _seed_match_and_prediction(session, 3, status="FT", home_score=1, away_score=1)
    reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    pred = session.execute(
        models.Prediction.__table__.select().where(
            models.Prediction.match_external_id == 3
        )
    ).fetchone()
    assert pred.actual_outcome == "draw"


def test_reconcile_skips_non_finished_matches(session):
    _seed_match_and_prediction(session, 4, status="NS", home_score=None, away_score=None)
    r = reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    assert r.scanned == 1
    assert r.updated == 0
    assert r.match_not_finished == 1


def test_reconcile_is_idempotent_after_first_pass(session):
    """Bir kere doldurulan satır, ikinci çağrıda taranmamalı (actual_outcome NOT NULL filter)."""
    _seed_match_and_prediction(session, 5, status="FT", home_score=2, away_score=0)
    reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    # İkinci çağrı boş tara
    r2 = reconcile_pending_predictions(session, sport=football.SPORT_NAME)
    assert r2.scanned == 0
    assert r2.updated == 0


def test_reconcile_job_registered_in_scheduler():
    """JobSpec scheduler registry'sinde — runner çağırabilir."""
    spec = get("reconcile_predictions")
    assert spec.name == "reconcile_predictions"
    assert callable(spec.handler)
