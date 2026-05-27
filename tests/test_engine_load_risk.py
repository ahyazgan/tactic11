"""engine.load v2 — risk_level + back_to_back."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.engine.load import compute_player_load


@dataclass(frozen=True)
class _App:
    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime


def _app(pid: int, mid: int, minutes: int, days_ago: int, now: datetime) -> _App:
    return _App("football", pid, mid, minutes, now - timedelta(days=days_ago))


def test_low_risk_for_sparse_appearances():
    now = datetime.now(UTC)
    r = compute_player_load(
        1, [_app(1, 100, 90, 10, now)], window_days=14, now=now,
    )
    # 90 dk / 14g * 7 = 45 dk/hafta → low
    assert r.value.risk_level == "low"
    assert r.value.high_load is False


def test_medium_risk_180_per_week():
    now = datetime.now(UTC)
    apps = [_app(1, 100 + i, 90, i * 3 + 1, now) for i in range(4)]
    # 360 dk / 14g * 7 = 180 dk/hafta → medium
    r = compute_player_load(1, apps, window_days=14, now=now)
    assert r.value.risk_level == "medium"


def test_high_risk_270_per_week():
    """Dakika eşiği high (270/hafta) ama back-to-back < 3 → 'high' (extreme değil).

    Window=7g: 3 maç 90'ar dk, 3 gün arayla (days_ago=1, 4, 7).
    270 dk / 7g * 7 = 270 → exactly high threshold.
    5-günlük pencerede max 2 maç ({1,4} ya da {4,7}) → b2b=2 → extreme tetiklenmez.
    """
    now = datetime.now(UTC)
    apps = [_app(1, i, 90, 1 + i * 3, now) for i in (0, 1, 2)]
    r = compute_player_load(1, apps, window_days=7, now=now)
    assert r.value.minutes_per_week >= 270
    assert r.value.back_to_back_count < 3
    assert r.value.risk_level == "high"
    assert r.value.high_load is True


def test_extreme_risk_back_to_back_three_in_five_days():
    """5 günde 3 maç → extreme (yüksek dakika olmasa bile)."""
    now = datetime.now(UTC)
    apps = [
        _app(1, 100, 60, 1, now),
        _app(1, 101, 60, 3, now),
        _app(1, 102, 60, 5, now),
    ]
    r = compute_player_load(1, apps, window_days=14, now=now)
    assert r.value.back_to_back_count == 3
    assert r.value.risk_level == "extreme"


def test_extreme_risk_360_per_week():
    """360+ dk/hafta tek başına extreme."""
    now = datetime.now(UTC)
    apps = [_app(1, 100 + i, 90, i * 2 + 1, now) for i in range(8)]
    # 720 dk / 14g * 7 = 360 → extreme
    r = compute_player_load(1, apps, window_days=14, now=now)
    assert r.value.risk_level == "extreme"


def test_back_to_back_count_for_spread_appearances():
    """7 günden geniş aralıklı maçlar → max 5-günlük pencerede 1 maç."""
    now = datetime.now(UTC)
    apps = [
        _app(1, 100, 90, 1, now),
        _app(1, 101, 90, 10, now),  # 9 gün ara → ayrı pencere
        _app(1, 102, 90, 20, now),  # 10 gün ara → ayrı pencere
    ]
    r = compute_player_load(1, apps, window_days=30, now=now)
    assert r.value.back_to_back_count == 1


def test_audit_includes_risk_thresholds():
    now = datetime.now(UTC)
    r = compute_player_load(
        1, [_app(1, 100, 90, 1, now)], window_days=14, now=now,
    )
    assert "risk_thresholds_min_per_week" in r.audit.inputs
    assert "back_to_back_window_days" in r.audit.inputs
    assert r.audit.engine_version == "2"
