from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import Match
from app.engine.schedule import compute_schedule
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


def test_schedule_counts_upcoming_for_team_only():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=2),
        _match(2, 614, 611, days_ahead=5),
        _match(3, 998, 607, days_ahead=3),  # 611 yok, dışarıda
    ]
    r = compute_schedule(611, matches, now=now).value
    assert r.upcoming_count == 2
    assert r.matches_next_7d == 2
    assert r.matches_next_14d == 2


def test_schedule_ignores_past_and_finished():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=-3),  # geçmiş
        _match(2, 614, 611, days_ahead=5, status="FT"),  # finished
        _match(3, 611, 998, days_ahead=10, status="NS"),
    ]
    r = compute_schedule(611, matches, now=now).value
    assert r.upcoming_count == 1


def test_schedule_days_until_next_match():
    now = datetime.now(UTC)
    matches = [_match(1, 611, 607, days_ahead=7)]
    r = compute_schedule(611, matches, now=now).value
    assert r.days_until_next_match == pytest.approx(7.0, abs=0.01)


def test_schedule_no_upcoming_matches():
    now = datetime.now(UTC)
    r = compute_schedule(611, [], now=now).value
    assert r.upcoming_count == 0
    assert r.days_until_next_match is None
    assert r.dense_schedule is False
    assert r.next_kickoffs == []


def test_schedule_dense_flag_for_3_in_7_days():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=1),
        _match(2, 614, 611, days_ahead=4),
        _match(3, 611, 998, days_ahead=6),
        _match(4, 611, 607, days_ahead=20),
    ]
    r = compute_schedule(611, matches, now=now).value
    assert r.matches_next_7d == 3
    assert r.dense_schedule is True


def test_schedule_respects_horizon():
    now = datetime.now(UTC)
    matches = [
        _match(1, 611, 607, days_ahead=5),
        _match(2, 614, 611, days_ahead=40),  # horizon dışı
    ]
    r = compute_schedule(611, matches, now=now, horizon_days=30).value
    assert r.upcoming_count == 1


def test_schedule_audit_carries_inputs():
    now = datetime.now(UTC)
    res = compute_schedule(611, [_match(1, 611, 607, days_ahead=2)], now=now, horizon_days=14)
    assert res.audit.engine == "engine.schedule"
    assert res.audit.inputs["horizon_days"] == 14
    assert res.audit.inputs["considered_match_ids"] == [1]
