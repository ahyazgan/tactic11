from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.form import compute_form
from app.engine.matchup import compute_matchup
from app.engine.opponent import compute_head_to_head
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


def _form_for(team_id, matches):
    return compute_form(team_id, matches, last_n=10).value


def test_matchup_form_delta_positive_when_home_stronger():
    # 611 evde 3 galibiyet (yüksek ppg), 607 ise 2 mağlubiyet (düşük ppg).
    home_matches = [
        _m(1, 611, 998, 3, 0, 5),
        _m(2, 611, 614, 2, 0, 10),
        _m(3, 611, 607, 4, 1, 15),
    ]
    away_matches = [
        _m(4, 998, 607, 2, 0, 4),
        _m(5, 614, 607, 3, 0, 8),
    ]
    home_form = _form_for(611, home_matches)
    away_form = _form_for(607, away_matches)
    h2h = compute_head_to_head(611, 607, []).value

    r = compute_matchup(home_form, away_form, h2h, home_team_id=611, away_team_id=607).value
    assert r.form_delta_ppg > 0  # ev ppg > dep ppg
    assert r.form_delta_goal_diff > 0
    assert r.home_advantage_factor == pytest.approx(1.0)  # ev sahibi olduğu maçların hepsini kazandı
    assert r.advantage_score > 0


def test_matchup_h2h_dominance_perspective_flipped_when_b_is_home():
    """HeadToHead team_a/b sıralaması home_team_id'den bağımsız olabilir;
    matchup ev sahibi perspektifine göre işareti çevirir."""
    # H2H'te team_a=607 (deplasman) ise A baskınsa h2h_dominance negatif olmalı (ev için kötü).
    h2h_matches = [
        _m(1, 607, 611, 2, 0, 30),
        _m(2, 611, 607, 0, 1, 20),
    ]
    # team_a_id ne olursa olsun compute_head_to_head sıralı çağrıyı kabul eder; biz a=607 verelim
    h2h = compute_head_to_head(607, 611, h2h_matches).value
    # 607 (a) 2 galibiyet, 611 (b) 0 → a_dominance = 100. Ama home_team_id=611 → flip → -100

    empty_form = _form_for(999, [])  # boş form (matches_played=0); shape için
    r = compute_matchup(
        empty_form, empty_form, h2h,
        home_team_id=611, away_team_id=607,
    ).value
    assert r.h2h_dominance == pytest.approx(-100.0)


def test_matchup_h2h_dominance_zero_when_no_h2h_matches():
    empty_form = _form_for(999, [])
    h2h = compute_head_to_head(611, 607, []).value
    r = compute_matchup(empty_form, empty_form, h2h, home_team_id=611, away_team_id=607).value
    assert r.h2h_dominance == 0.0


def test_matchup_audit_engine_name():
    empty_form = _form_for(999, [])
    h2h = compute_head_to_head(611, 607, []).value
    res = compute_matchup(empty_form, empty_form, h2h, home_team_id=611, away_team_id=607)
    assert res.audit.engine == "engine.matchup"
    assert res.audit.subject_id == 611
    assert res.audit.inputs["away_team_id"] == 607
