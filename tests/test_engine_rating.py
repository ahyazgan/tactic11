from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
        kickoff=datetime.now(timezone.utc) - timedelta(days=days_ago),
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
