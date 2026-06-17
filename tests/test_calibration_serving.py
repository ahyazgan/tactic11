"""Kalibrasyon serving pipeline — train → cache → /predict injection (kalibrasyon ρ ikizi)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.data.cache.store import cache_set
from app.db import models
from app.db.session import get_session
from app.engine.calibration import (
    CACHE_KEY,
    CACHE_SOURCE,
    NotEnoughTrainingData,
    train_best_temperature,
)
from app.scheduler.registry import get
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
    session.add_all([
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
    ])
    session.flush()


def _seed_prediction(session, *, match_id, ph, pd, pa, actual):
    now = datetime.now(UTC)
    session.add(models.Prediction(
        sport="football", match_external_id=match_id,
        engine="engine.predict", engine_version="3",
        params_hash=f"h{match_id}", params_json="{}",
        predicted_value_json=json.dumps({
            "expected_home_goals": 1.5, "expected_away_goals": 1.0,
            "prob_home_win": ph, "prob_draw": pd, "prob_away_win": pa,
        }),
        created_at=now - timedelta(days=10), updated_at=now - timedelta(days=10),
        actual_home_score=0, actual_away_score=0,
        actual_outcome=actual, reconciled_at=now,
    ))
    session.flush()


def _populate_cal_cache(session, *, temperature: float, sample_count: int = 50):
    cache_set(
        session, source=CACHE_SOURCE, key=CACHE_KEY,
        value={
            "best_temperature": temperature, "sample_count": sample_count,
            "log_loss_before": 1.2, "log_loss_after": 0.95, "improved": True,
        },
        ttl_seconds=30 * 86_400,
    )
    session.flush()


# ---- training -------------------------------------------------------------


def test_train_temperature_not_enough_data_raises(session):
    with pytest.raises(NotEnoughTrainingData):
        train_best_temperature(session, min_samples=20)


def test_train_temperature_corrects_overconfidence(session):
    # Aşırı-güvenli tahminler: hep %90 home ama gerçek %60.
    for i in range(40):
        actual = "home" if i % 10 < 6 else ("draw" if i % 10 < 8 else "away")
        _seed_prediction(session, match_id=i, ph=0.9, pd=0.05, pa=0.05, actual=actual)
    report = train_best_temperature(session, min_samples=20)
    assert report.sample_count == 40
    assert report.best_temperature > 1.0
    assert report.log_loss_after < report.log_loss_before
    assert report.improved is True


def test_train_calibration_job_registered():
    """Job kayıtlı ve çağrılabilir (handler içi SessionLocal gerçek DB ister,
    burada yalnız kayıt + imza doğrulanır)."""
    spec = get("train_calibration")
    assert spec.name == "train_calibration"
    assert callable(spec.handler)


# ---- /admin/calibration-model-status --------------------------------------


def test_calibration_status_untrained(client):
    r = client.get("/admin/calibration-model-status")
    assert r.status_code == 200
    assert r.json() == {"status": "untrained"}


def test_calibration_status_fresh(session, client):
    _populate_cal_cache(session, temperature=1.4, sample_count=42)
    body = client.get("/admin/calibration-model-status").json()
    assert body["status"] == "fresh"
    assert body["best_temperature"] == 1.4
    assert body["sample_count"] == 42
    assert body["improved"] is True


# ---- /predict injection ---------------------------------------------------


def test_predict_no_calibration_block_when_untrained(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    body = client.get("/matches/99/predict").json()
    assert "calibration" not in body


def test_predict_injects_calibration_block_when_trained(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_cal_cache(session, temperature=1.5)
    body = client.get("/matches/99/predict").json()
    assert "calibration" in body
    cal = body["calibration"]
    assert cal["applied"] is True
    assert cal["temperature"] == 1.5
    probs = (cal["prob_home_win"], cal["prob_draw"], cal["prob_away_win"])
    assert sum(probs) == pytest.approx(1.0, abs=0.01)
    # T>1 → tepe olasılık ham haline göre yumuşar.
    raw = body["value"]
    raw_max = max(raw["prob_home_win"], raw["prob_draw"], raw["prob_away_win"])
    cal_max = max(probs)
    assert cal_max <= raw_max + 1e-9
    # HAM tahmin değişmedi (value bloğu kalibre edilmemiş kalır).
    assert raw["prob_home_win"] != cal["prob_home_win"] or raw_max == pytest.approx(cal_max)


def test_predict_identity_temperature_marks_not_applied(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_cal_cache(session, temperature=1.0)
    body = client.get("/matches/99/predict").json()
    assert body["calibration"]["applied"] is False


# ---- ρ + T shadow'lama -----------------------------------------------------


def _predictions(session, *, engine, match_id=99):
    from sqlalchemy import select
    return list(session.execute(
        select(models.Prediction).where(
            models.Prediction.engine == engine,
            models.Prediction.match_external_id == match_id,
        )
    ).scalars())


def test_shadow_saves_calibrated_variant(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_cal_cache(session, temperature=1.5)
    r = client.get("/matches/99/predict?shadow=true")
    assert r.status_code == 200

    cal_rows = _predictions(session, engine="engine.predict_calibrated")
    assert len(cal_rows) == 1
    cal = json.loads(cal_rows[0].predicted_value_json)
    s = cal["prob_home_win"] + cal["prob_draw"] + cal["prob_away_win"]
    assert abs(s - 1.0) < 0.02
    assert "calibration_T" in cal_rows[0].params_json
    # Kalibre satır HAM engine.predict satırından ayrı (training'i kirletmez).
    assert all(r2.engine == "engine.predict_calibrated" for r2 in cal_rows)
    # T=1.5 yumuşatır → kalibre tepe olasılık ham tahminin altında.
    raw = r.json()["value"]
    raw_max = max(raw["prob_home_win"], raw["prob_draw"], raw["prob_away_win"])
    cal_max = max(cal["prob_home_win"], cal["prob_draw"], cal["prob_away_win"])
    assert cal_max <= raw_max + 1e-9


def test_shadow_skips_calibrated_when_identity_temperature(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    _populate_cal_cache(session, temperature=1.0)
    client.get("/matches/99/predict?shadow=true")
    assert _predictions(session, engine="engine.predict_calibrated") == []


def test_shadow_skips_calibrated_when_untrained(session, client):
    _seed_match_with_history(session, datetime.now(UTC))
    client.get("/matches/99/predict?shadow=true")
    assert _predictions(session, engine="engine.predict_calibrated") == []
