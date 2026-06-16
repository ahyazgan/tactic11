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


def _form_for(team_id, scoring_avg, conceding_avg=1.0, n=8):
    """Yardımcı — takımın goals_for_per_match=scoring_avg ve
    goals_against_per_match=conceding_avg olacak şekilde matches üret.

    Tüm maçlarda takım ev sahibi: goals_for += home_score, goals_against +=
    away_score (predict yalnız bu iki oranı + matches_played'i kullanır)."""
    matches = []
    gf = int(round(scoring_avg))
    ga = int(round(conceding_avg))
    for i in range(n):
        matches.append(_m(i, team_id, 999 - i, gf, ga, i + 1))
    return compute_form(team_id, matches, last_n=n).value


def test_predict_probabilities_sum_to_one():
    home_f = _form_for(611, scoring_avg=1.5)
    away_f = _form_for(607, scoring_avg=1.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    total = p.prob_home_win + p.prob_draw + p.prob_away_win
    assert total == pytest.approx(1.0, abs=0.01)  # max_goals=10 nedeniyle hafif kuyruk kaybı


def test_predict_home_favored_when_higher_lambda():
    # Ev sahibi güçlü saldırı + sağlam savunma; deplasman zayıf + delik savunma.
    home_f = _form_for(611, scoring_avg=2.5, conceding_avg=0.5)
    away_f = _form_for(607, scoring_avg=0.5, conceding_avg=2.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.prob_home_win > p.prob_away_win
    assert p.prob_home_win > p.prob_draw
    assert p.expected_home_goals > p.expected_away_goals


def test_predict_symmetric_when_same_lambda():
    """Aynı saldırı+savunma ve hfa=1.0 → home_win ≈ away_win."""
    home_f = _form_for(611, scoring_avg=1.0, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    p = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607, home_advantage=1.0
    ).value
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
    """En olası skor, olasılık matrisindeki maksimumla aynı (eşit takım, hfa=1).

    λ=1 için (0,0)/(1,1) saf Poisson'da ~0.135; DC (ρ=-0.12) τ=1.12 ile
    her iki hücreyi ~0.151'e çıkarır.
    """
    home_f = _form_for(611, scoring_avg=1.0, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    p = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607, home_advantage=1.0
    ).value
    assert p.most_likely_score in [(0, 0), (1, 1)]
    assert p.most_likely_score_prob == pytest.approx(0.151, abs=0.01)


def test_predict_baseline_reproduces_own_attack():
    """w=0, hfa=1, ρ=0 → eski saf bağımsız-Poisson: λ = kendi gol ortalaması."""
    home_f = _form_for(611, scoring_avg=2.0, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=3.0)
    p = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607,
        rho=0.0, home_advantage=1.0, opponent_weight=0.0,
    ).value
    # Baseline: λ rakipten bağımsız, yalnız kendi atağı.
    assert p.expected_home_goals == pytest.approx(2.0, abs=0.001)
    assert p.expected_away_goals == pytest.approx(1.0, abs=0.001)
    assert p.opponent_weight_used == 0.0
    assert p.home_advantage_used == 1.0


def test_predict_opponent_defense_raises_lambda():
    """Aynı ev sahibi atağı; rakip savunması delikleştikçe λ_home artar."""
    home_f = _form_for(611, scoring_avg=1.5, conceding_avg=1.0)
    stingy = _form_for(607, scoring_avg=1.0, conceding_avg=0.3)   # sağlam savunma
    leaky = _form_for(608, scoring_avg=1.0, conceding_avg=2.5)    # delik savunma
    p_stingy = compute_predict(
        home_f, stingy, home_team_id=611, away_team_id=607, home_advantage=1.0
    ).value
    p_leaky = compute_predict(
        home_f, leaky, home_team_id=611, away_team_id=608, home_advantage=1.0
    ).value
    assert p_leaky.expected_home_goals > p_stingy.expected_home_goals
    assert p_leaky.prob_home_win > p_stingy.prob_home_win


def test_predict_home_advantage_boosts_home():
    """hfa>1 → λ_home ↑, λ_away ↓, ev sahibi kazanma olasılığı artar."""
    home_f = _form_for(611, scoring_avg=1.2, conceding_avg=1.2)
    away_f = _form_for(607, scoring_avg=1.2, conceding_avg=1.2)
    neutral = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607, home_advantage=1.0
    ).value
    boosted = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607, home_advantage=1.3
    ).value
    assert boosted.expected_home_goals > neutral.expected_home_goals
    assert boosted.expected_away_goals < neutral.expected_away_goals
    assert boosted.prob_home_win > neutral.prob_home_win


def test_predict_rho_zero_falls_back_to_pure_poisson():
    """ρ=0 + eşit takım + hfa=1 → saf Poisson: P(0,0)=P(1,1)≈0.135."""
    home_f = _form_for(611, scoring_avg=1.0, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    p = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607,
        rho=0.0, home_advantage=1.0,
    ).value
    assert p.most_likely_score_prob == pytest.approx(0.135, abs=0.01)
    assert p.rho_used == 0.0


def test_predict_dixon_coles_bumps_low_score_cells():
    """Negatif ρ ile (0-0)/(1-1) hücresi yukarı, (0-1)/(1-0) aşağı."""
    home_f = _form_for(611, scoring_avg=1.0, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    p_poisson = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607,
        rho=0.0, home_advantage=1.0,
    ).value
    p_dc = compute_predict(
        home_f, away_f, home_team_id=611, away_team_id=607, home_advantage=1.0
    ).value  # ρ=-0.12

    assert p_dc.prob_draw > p_poisson.prob_draw
    total_dc = p_dc.prob_home_win + p_dc.prob_away_win
    total_poisson = p_poisson.prob_home_win + p_poisson.prob_away_win
    assert total_dc < total_poisson
    assert (p_dc.prob_home_win + p_dc.prob_draw + p_dc.prob_away_win) == pytest.approx(1.0, abs=0.01)


def test_predict_audit_carries_formula_and_inputs():
    home_f = _form_for(611, scoring_avg=1.5, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    res = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607)
    assert res.audit.engine == "engine.predict"
    assert res.audit.engine_version == "3"
    assert "Poisson" in res.audit.formula
    assert "Dixon-Coles" in res.audit.formula
    assert res.audit.inputs["rho"] == pytest.approx(-0.12)
    assert res.audit.inputs["home_advantage"] == pytest.approx(1.15)
    assert res.audit.inputs["opponent_weight"] == pytest.approx(0.65)
    assert res.audit.inputs["away_defense"] == pytest.approx(1.0)
    assert res.audit.inputs["min_confident_sample"] == 5


def test_predict_zero_goals_doesnt_crash():
    """Edge case: ev sahibi 0 gol atmış (goals_for_per_match=0)."""
    home_f = _form_for(611, scoring_avg=0.0, conceding_avg=1.5)
    away_f = _form_for(607, scoring_avg=1.5, conceding_avg=1.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.prob_home_win == pytest.approx(0.0, abs=0.001)
    assert p.prob_away_win > 0.5  # dep favori


def test_predict_all_zero_data_falls_back_safely():
    """league_avg=0 (hiç gol verisi yok) → div-by-zero yok, λ=0 baseline."""
    home_f = _form_for(611, scoring_avg=0.0, conceding_avg=0.0)
    away_f = _form_for(607, scoring_avg=0.0, conceding_avg=0.0)
    p = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607).value
    assert p.league_baseline == 0.0
    # λ=0 her iki taraf → (0,0) kesin → beraberlik baskın
    assert p.prob_draw == pytest.approx(1.0, abs=0.001)


def test_predict_carries_confidence():
    home_f = _form_for(611, scoring_avg=1.5, conceding_avg=1.0)
    away_f = _form_for(607, scoring_avg=1.0, conceding_avg=1.0)
    res = compute_predict(home_f, away_f, home_team_id=611, away_team_id=607)
    assert res.confidence is not None
    assert 0.0 <= res.confidence.score <= 1.0
    assert res.confidence.label in ("yüksek", "orta", "düşük")
