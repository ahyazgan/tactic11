"""engine.score_prediction — kesin-skor dağılımı + market olasılıkları."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.form import compute_form
from app.engine.score_prediction import compute_score_prediction
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
    matches = [
        _m(i, team_id, 999 - i, int(round(scoring_avg)), 0, i + 1)
        for i in range(n)
    ]
    return compute_form(team_id, matches, last_n=n).value


def _predict(home_avg=1.5, away_avg=1.0, **kw):
    return compute_score_prediction(
        _form_for(611, home_avg), _form_for(607, away_avg),
        home_team_id=611, away_team_id=607, **kw,
    ).value


def test_over_under_2_5_are_complementary():
    p = _predict()
    assert p.prob_over_2_5 + p.prob_under_2_5 == pytest.approx(1.0, abs=1e-6)


def test_over_lines_monotonic():
    """Daha yüksek çizgiyi geçmek daha zor → over_1_5 ≥ over_2_5 ≥ over_3_5."""
    p = _predict()
    assert p.prob_over_1_5 >= p.prob_over_2_5 >= p.prob_over_3_5


def test_top_scores_sorted_and_capped():
    p = _predict(top_n=3)
    assert len(p.top_scores) == 3
    probs = [prob for _h, _a, prob in p.top_scores]
    assert probs == sorted(probs, reverse=True)
    # En olası skor toplam matristen anlamlı pay almalı
    assert 0.0 < probs[0] <= 1.0


def test_all_market_probs_in_unit_interval():
    p = _predict()
    for v in (
        p.prob_btts, p.prob_over_1_5, p.prob_over_2_5, p.prob_over_3_5,
        p.prob_under_2_5, p.prob_home_clean_sheet, p.prob_away_clean_sheet,
    ):
        assert 0.0 <= v <= 1.0


def test_expected_total_is_sum_of_lambdas():
    p = _predict(home_avg=2.0, away_avg=1.0)
    assert p.expected_total_goals == pytest.approx(
        p.expected_home_goals + p.expected_away_goals, abs=1e-6
    )


def test_higher_scoring_increases_btts_and_over():
    low = _predict(home_avg=0.5, away_avg=0.5)
    high = _predict(home_avg=2.5, away_avg=2.5)
    assert high.prob_btts > low.prob_btts
    assert high.prob_over_2_5 > low.prob_over_2_5


def test_strong_home_raises_away_clean_sheet_prob():
    """Ev sahibi çok, deplasman az gol atıyorsa: deplasmanın gol atmama
    olasılığı (= ev sahibi clean sheet) yüksek olmalı."""
    p = _predict(home_avg=2.5, away_avg=0.3)
    # away_avg düşük → deplasman çok az gol → home_clean_sheet (away=0) yüksek
    assert p.prob_home_clean_sheet > 0.5


def test_low_confidence_flag_for_small_sample():
    home = _form_for(611, 1.5, n=2)
    away = _form_for(607, 1.0, n=2)
    p = compute_score_prediction(
        home, away, home_team_id=611, away_team_id=607,
    ).value
    assert p.low_confidence is True
    assert p.sample_size == 2


def test_audit_record_present():
    r = compute_score_prediction(
        _form_for(611, 1.5), _form_for(607, 1.0),
        home_team_id=611, away_team_id=607,
    )
    assert r.audit.engine == "engine.score_prediction"
    assert r.confidence is not None
