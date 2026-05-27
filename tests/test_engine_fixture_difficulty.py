from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.fixture_difficulty import compute_fixture_difficulty
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


def test_difficulty_picks_upcoming_only_for_team():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),
        _match(2, 614, 611, days_ahead=5),
        _match(3, 998, 627, days_ahead=3),  # 611 yok, dışarıda
        _match(4, 611, 998, days_ahead=-3),  # geçmiş, dışarıda
    ]
    ratings = {607: 80.0, 614: 60.0, 998: 50.0, 627: 40.0}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 2
    assert r.matches_unknown_opponent == 0
    # Düz ortalama: (80 + 60) / 2 = 70
    assert r.avg_opponent_rating == pytest.approx(70.0)
    # Ev/dep ayrımı
    assert r.home_match_count == 1  # match 1: 611 home
    assert r.away_match_count == 1  # match 2: 611 away


def test_difficulty_marks_unknown_opponents():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),
        _match(2, 611, 999, days_ahead=5),  # rating yok
    ]
    ratings = {607: 80.0}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 1
    assert r.matches_unknown_opponent == 1
    assert r.avg_opponent_rating == pytest.approx(80.0)


def test_difficulty_time_weights_favor_near_matches():
    """Yakın maç ağırlıklı; uzaktaki kolay rakip ortalamayı bozmasın."""
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=1),  # yakın, zor (w ~1.0)
        _match(2, 611, 998, days_ahead=27),  # uzak, kolay (w taban'a yakın)
    ]
    ratings = {607: 100.0, 998: 20.0}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    # Düz: 60; weighted yakın 100'e doğru çekilmeli
    assert r.avg_opponent_rating == pytest.approx(60.0)
    assert r.weighted_difficulty > r.avg_opponent_rating
    assert r.weighted_difficulty > 60.0


def test_difficulty_hardest_and_easiest():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),
        _match(2, 611, 614, days_ahead=5),
        _match(3, 611, 998, days_ahead=9),
    ]
    ratings = {607: 90.0, 614: 60.0, 998: 30.0}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.hardest_opponent_id == 607
    assert r.hardest_opponent_rating == pytest.approx(90.0)
    assert r.easiest_opponent_id == 998
    assert r.easiest_opponent_rating == pytest.approx(30.0)


def test_difficulty_empty_when_no_upcoming():
    now = datetime.now(UTC)
    r = compute_fixture_difficulty(611, [], {}, now=now).value
    assert r.matches_considered == 0
    assert r.matches_unknown_opponent == 0
    assert r.avg_opponent_rating == 0.0
    assert r.weighted_difficulty == 0.0
    assert r.hardest_opponent_id is None
    assert r.easiest_opponent_id is None


def test_difficulty_all_unknown_returns_zero_avg():
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=2)]
    r = compute_fixture_difficulty(611, matches, {}, now=now).value
    assert r.matches_considered == 0
    assert r.matches_unknown_opponent == 1
    assert r.avg_opponent_rating == 0.0
    assert r.hardest_opponent_id is None


def test_difficulty_ignores_finished_matches():
    """FT statüsü 'geçmiş' kabul edilir, ufukta sayılmaz."""
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=5, status="FT"),  # finished
        _match(2, 611, 998, days_ahead=10, status="NS"),
    ]
    ratings = {607: 90.0, 998: 50.0}
    r = compute_fixture_difficulty(611, matches, ratings, now=now).value
    assert r.matches_considered == 1
    assert r.hardest_opponent_id == 998


def test_difficulty_audit_carries_inputs():
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=2)]
    res = compute_fixture_difficulty(611, matches, {607: 75.0}, now=now)
    assert res.audit.engine == "engine.fixture_difficulty"
    assert res.audit.inputs["upcoming_match_ids"] == [1]
    assert res.audit.inputs["known_opponents"] == [607]
