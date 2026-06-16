from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain import Match
from app.engine.rating import compute_team_rating
from app.engine.rating.compute import GD_WEIGHT, PPG_WEIGHT
from app.sports import football


def _match(ext_id, home, away, hs, as_, days_ago=1):
    return Match(
        sport=football.SPORT_NAME,
        external_id=ext_id,
        league_external_id=203,
        season=2024,
        kickoff=datetime.now(UTC) - timedelta(days=days_ago),
        status="FT",
        home_team_external_id=home,
        away_team_external_id=away,
        home_score=hs,
        away_score=as_,
    )


def test_rating_formula_matches_form_inputs():
    # 2W, 1D, 1L; goals 5-4 -> ppg=1.75, gdpm=0.25
    matches = [
        _match(1, 611, 607, 2, 1, 10),
        _match(2, 614, 611, 1, 3, 7),
        _match(3, 611, 998, 0, 0, 3),
        _match(4, 998, 611, 2, 0, 1),
    ]
    res = compute_team_rating(611, matches, last_n=10)
    expected = 1.75 * PPG_WEIGHT + 0.25 * GD_WEIGHT
    assert res.value.rating == round(expected, 3)
    assert res.value.matches_considered == 4


def test_zero_matches_zero_rating():
    res = compute_team_rating(611, [], last_n=5)
    assert res.value.rating == 0.0
    assert res.value.matches_considered == 0
    assert res.value.home_rating == 0.0
    assert res.value.away_rating == 0.0
    assert res.value.home_matches == 0
    assert res.value.away_matches == 0


def test_home_rating_separates_home_only_matches():
    """Takım evde çok güçlü, dep'te zayıf → home_rating > away_rating."""
    matches = [
        # Evde 3 maç: hep galibiyet, hepsi 2 farkla
        _match(1, 611, 607, 3, 1, 30),
        _match(2, 611, 614, 2, 0, 20),
        _match(3, 611, 998, 2, 0, 10),
        # Dep'te 3 maç: hep mağlubiyet
        _match(4, 607, 611, 2, 0, 25),
        _match(5, 614, 611, 1, 0, 15),
        _match(6, 998, 611, 3, 1, 5),
    ]
    res = compute_team_rating(611, matches, last_n=10).value
    assert res.home_matches == 3
    assert res.away_matches == 3
    # Evde 9 puan / 3 maç = ppg 3.0, gd_per = +1.67
    # Dep'te 0 puan / 3 maç = ppg 0.0, gd_per = -1.33
    assert res.home_rating > res.away_rating
    assert res.home_rating > res.rating  # overall'dan yüksek (evdeki kısmı)
    assert res.away_rating < res.rating  # overall'dan düşük (depteki kısmı)
    # Sayısal: home = 3.0*50 + 1.667*10 ≈ 166.67
    assert res.home_rating > 160
    # Dep: 0*50 + (-1.333)*10 ≈ -13.33
    assert res.away_rating < 0


def test_home_only_team_has_zero_away_rating():
    """Sadece evde oynamış takım → away_rating=0.0, home_matches>0."""
    matches = [_match(1, 611, 607, 2, 1, 10)]
    res = compute_team_rating(611, matches, last_n=5).value
    assert res.home_matches == 1
    assert res.away_matches == 0
    assert res.home_rating > 0  # 1 galibiyet
    assert res.away_rating == 0.0


def test_rating_audit_carries_split_inputs():
    matches = [
        _match(1, 611, 607, 2, 1, 10),
        _match(2, 614, 611, 1, 3, 5),
    ]
    res = compute_team_rating(611, matches, last_n=10)
    assert res.audit.engine_version == "2"
    assert res.audit.inputs["home_matches"] == 1
    assert res.audit.inputs["away_matches"] == 1
    assert "home_rating" in res.audit.formula
    assert "away_rating" in res.audit.formula


def test_rating_carries_confidence():
    matches = [
        _match(1, 611, 607, 2, 1, 10),
        _match(2, 614, 611, 1, 3, 7),
        _match(3, 611, 998, 0, 0, 3),
        _match(4, 998, 611, 2, 0, 1),
    ]
    res = compute_team_rating(611, matches, last_n=10)
    assert res.confidence is not None
    assert 0.0 <= res.confidence.score <= 1.0
    assert res.confidence.label in ("yüksek", "orta", "düşük")
