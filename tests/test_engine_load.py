from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain import PlayerAppearance
from app.engine.load import compute_player_load
from app.sports import football


def _app(player_id, match_id, minutes, days_ago, *, now: datetime):
    return PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        minutes=minutes,
        kickoff=now - timedelta(days=days_ago),
    )


def test_load_window_excludes_old_matches():
    now = datetime.now(timezone.utc)
    apps = [
        _app(7, 1, 90, days_ago=1, now=now),
        _app(7, 2, 70, days_ago=5, now=now),
        _app(7, 3, 90, days_ago=30, now=now),  # pencere dışı
    ]
    res = compute_player_load(7, apps, window_days=14, now=now)
    assert res.value.matches_in_window == 2
    assert res.value.minutes_in_window == 160
    assert res.value.minutes_per_match == 80.0


def test_load_filters_by_player_and_sport():
    now = datetime.now(timezone.utc)
    apps = [
        _app(7, 1, 90, days_ago=1, now=now),
        _app(8, 2, 90, days_ago=1, now=now),  # başka oyuncu
        PlayerAppearance(  # başka spor
            sport="basketball",
            player_external_id=7,
            match_external_id=3,
            minutes=30,
            kickoff=now - timedelta(days=1),
        ),
    ]
    res = compute_player_load(7, apps, now=now)
    assert res.value.matches_in_window == 1


def test_high_load_flag_trips_above_threshold():
    now = datetime.now(timezone.utc)
    apps = [
        _app(7, i, 90, days_ago=i, now=now) for i in range(1, 7)  # 6 maç, 14 gün
    ]
    res = compute_player_load(7, apps, window_days=14, now=now)
    # 540 dk / 14 gün * 7 ≈ 270 → eşik 270; sınırda True olmalı
    assert res.value.high_load is True
