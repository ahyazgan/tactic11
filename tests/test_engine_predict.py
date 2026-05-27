from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.form import compute_form
from app.engine.predict import compute_predict
from app.sports import football


def _m(ext_id, home, away, hs, as_, days_ago):
    return Match(
        sport=football.SPORT_NAME, external_id=ext_id,
        league_external_id=203, season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
        status="FT",
        home_team_external_id=home, away_team_external_id=away,
        home_score=hs, away_score=as_,
    )


def _form_for(team_id, scoring_avg, n=8):
    """Yardımcı — bir takımın goals_for_per_match'i tam scoring_avg olacak şekilde matches üret."""
    matches = []
    for i in range(n):
        # Her maçta tam scoring_avg gol attı gibi sayılsın diye yuvarla:
        gf = int(round(scoring_avg))
        matches.append(_m(i, team_id, 999 - i, gf, 0, i + 1))
    return compute_form(team_id, matches, last_n=n).value


def test_predict_probabilities_sum_to_one():
    home_f = _form_for(611, scoring_avg=1.5)
    away_f = _form_for(607, scoring_avg=1.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    total = p.prob_home_win + p.prob_draw + p.prob_away_win
    assert total == pytest.approx(1.0, abs=0.01)  # max_goals=10 nedeniyle hafif kuyruk kaybı


def test_predict_home_favored_when_higher_lambda():
    home_f = _form_for(611, scoring_avg=2.5)
    away_f = _form_for(607, scoring_avg=0.5)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.prob_home_win > p.prob_away_win
    assert p.prob_home_win > p.prob_draw
    assert p.expected_home_goals > p.expected_away_goals


def test_predict_symmetric_when_same_lambda():
    """λ eşitse home_win ≈ away_win, draw payı maksimum."""
    home_f = _form_for(611, scoring_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.prob_home_win == pytest.approx(p.prob_away_win, abs=0.001)


def test_predict_low_confidence_flag_when_few_matches():
    home_f = _form_for(611, scoring_avg=1.5, n=3)  # < 5 maç
    away_f = _form_for(607, scoring_avg=1.0, n=8)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.low_confidence is True
    assert p.sample_size == 3


def test_predict_no_low_confidence_with_5plus_matches():
    home_f = _form_for(611, scoring_avg=1.5, n=8)
    away_f = _form_for(607, scoring_avg=1.0, n=6)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.low_confidence is False
    assert p.sample_size == 6


def test_predict_most_likely_score_is_grid_max():
    """En olası skor, olasılık matrisindeki maksimumla aynı."""
    home_f = _form_for(611, scoring_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    # λ=1 için Poisson modu k=0 veya k=1; iki taraf da 1.0 ise (0,0) veya (1,1) olası.
    # Tam sayısal eşitlikten dolayı (0,0)'ın matrisinde değeri = e^-1·e^-1 ≈ 0.135
    # (1,1) = 1·e^-1·1·e^-1 ≈ 0.135 — aynı. En olası set: (0,0) veya (1,1).
    assert p.most_likely_score in [(0, 0), (1, 1)]
    assert p.most_likely_score_prob == pytest.approx(0.135, abs=0.01)


def test_predict_audit_carries_formula_and_inputs():
    home_f = _form_for(611, scoring_avg=1.5)
    away_f = _form_for(607, scoring_avg=1.0)
    res = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607)
    assert res.audit.engine == "engine.predict"
    assert "Poisson" in res.audit.formula
    assert res.audit.inputs["lam_home"] == 1.5 or res.audit.inputs["lam_home"] == 2.0  # round nedeniyle
    assert res.audit.inputs["min_confident_sample"] == 5


def test_predict_zero_goals_doesnt_crash():
    """Edge case: bir takım 0 gol atmış (form.goals_for_per_match=0)."""
    home_f = _form_for(611, scoring_avg=0.0)
    away_f = _form_for(607, scoring_avg=1.5)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    # Ev sahibi 0 gol atıyor → kazanma şansı çok düşük (ancak 0-0 = beraberlik)
    assert p.prob_home_win == pytest.approx(0.0, abs=0.001)
    assert p.prob_away_win > 0.5  # dep favori
