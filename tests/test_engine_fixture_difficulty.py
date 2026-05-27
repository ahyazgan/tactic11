from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.fixture_difficulty import OpponentRating, compute_fixture_difficulty
from app.sports import football


def _match(ext_id, home, away, days_ahead, status="NS"):
    return Match(
        sport=football.SPORT_NAME,
        external_id=ext_id,
        league_external_id=203,
        season=2024,
        kickoff=datetime.now(UTC) + timedelta(days=days_ahead),
        status=status,
        home_team_external_id=home,
        away_team_external_id=away,
        home_score=None,
        away_score=None,
    )


def _r(home=None, away=None, overall=None) -> OpponentRating:
    return OpponentRating(home_rating=home, away_rating=away, overall_rating=overall)


def test_difficulty_picks_upcoming_only_for_team():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),
        _match(2, 614, 611, days_ahead=5),
        _match(3, 998, 627, days_ahead=3),  # 611 yok, dışarıda
        _match(4, 611, 998, days_ahead=-3),  # geçmiş, dışarıda
    ]
    ratings = {
        607: _r(home=80, away=70, overall=75),
        614: _r(home=60, away=50, overall=55),
        998: _r(overall=50),
        627: _r(overall=40),
    }
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 2
    assert r.matches_unknown_opponent == 0
    # match 1: opp=607 ev sahibi=611 → opp dep → 607.away_rating = 70
    # match 2: opp=614 ev sahibi=614 → opp ev → 614.home_rating = 60
    # avg = (70 + 60) / 2 = 65
    assert r.avg_opponent_rating == pytest.approx(65.0)
    assert r.home_match_count == 1
    assert r.away_match_count == 1


def test_difficulty_picks_side_specific_rating_per_match():
    """Aynı rakip iki maçta iki farklı tarafta → iki farklı rating kullanılır."""
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),  # 607 dep → away_rating
        _match(2, 607, 611, days_ahead=10),  # 607 ev → home_rating
    ]
    ratings = {607: _r(home=100, away=20, overall=50)}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 2
    # avg = (away=20 + home=100) / 2 = 60
    assert r.avg_opponent_rating == pytest.approx(60.0)
    # hardest = 100 (607 evinde), easiest = 20 (607 deplasmanda)
    assert r.hardest_opponent_rating == pytest.approx(100.0)
    assert r.easiest_opponent_rating == pytest.approx(20.0)


def test_difficulty_falls_back_to_overall_when_side_missing():
    """Side-specific yoksa overall fallback devreye girer."""
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=2)]
    # 607 dep → away_rating ararız; ama sadece overall var
    ratings = {607: _r(overall=75)}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 1
    assert r.avg_opponent_rating == pytest.approx(75.0)


def test_difficulty_marks_unknown_when_no_rating_available():
    """Side-specific yok + overall yok → kapsam dışı."""
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),  # 607 için hiçbir rating yok
        _match(2, 611, 614, days_ahead=5),  # 614 sadece overall
    ]
    ratings = {614: _r(overall=60)}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 1
    assert r.matches_unknown_opponent == 1


def test_difficulty_marks_unknown_when_opp_only_has_wrong_side():
    """Sadece home_rating var ama rakip o maçta dep'te → fallback overall'a, o da yok."""
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=2)]  # 607 dep → away ararız
    ratings = {607: _r(home=80)}  # sadece home
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 0
    assert r.matches_unknown_opponent == 1


def test_difficulty_time_weights_favor_near_matches():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=1),
        _match(2, 611, 998, days_ahead=27),
    ]
    ratings = {607: _r(away=100), 998: _r(away=20)}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.avg_opponent_rating == pytest.approx(60.0)
    assert r.weighted_difficulty > r.avg_opponent_rating
    assert r.weighted_difficulty > 60.0


def test_difficulty_empty_when_no_upcoming():
    now = datetime.now(UTC)
    r = compute_fixture_difficulty(611, [], {}, now=now).value
    assert r.matches_considered == 0
    assert r.matches_unknown_opponent == 0
    assert r.avg_opponent_rating == 0.0
    assert r.hardest_opponent_id is None


def test_difficulty_ignores_finished_matches():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=5, status="FT"),  # finished
        _match(2, 611, 998, days_ahead=10, status="NS"),
    ]
    ratings = {607: _r(overall=90), 998: _r(overall=50)}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 1
    assert r.hardest_opponent_id == 998


def test_difficulty_audit_carries_inputs_and_v2():
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=2)]
    res = compute_fixture_difficulty(611, matches, {607: _r(away=75)}, now=now)
    assert res.audit.engine == "engine.fixture_difficulty"
    assert res.audit.engine_version == "2"
    assert res.audit.inputs["upcoming_match_ids"] == [1]
    assert res.audit.inputs["known_opponents"] == [607]
    assert "side-specific" in res.audit.formula or "side" in res.audit.formula.lower()
