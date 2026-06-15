"""Minutes Management — sezon dakika planı + maraton riski."""
from __future__ import annotations

from app.engine.minutes_management import (
    PlayerMinutesInput,
    compute_minutes_management,
)


def _p(pid: int, age: int, minutes: list[float],
       injured_days: int | None = None, fixtures: int = 2) -> PlayerMinutesInput:
    return PlayerMinutesInput(
        player_external_id=pid, age=age,
        weekly_minutes_recent=minutes,
        days_since_last_injury=injured_days,
        matches_next_2_weeks=fixtures,
    )


def test_normal_team_no_rotation():
    """Normal yüklü 4 oyuncu, normal fikstür → rotation gereksiz."""
    players = [
        _p(1, 27, [60, 65, 70, 55], fixtures=2),
        _p(2, 24, [60, 60, 60, 60], fixtures=2),
        _p(3, 29, [70, 65, 60, 60], fixtures=2),
        _p(4, 22, [55, 60, 65, 70], fixtures=2),
    ]
    r = compute_minutes_management(players).value
    assert r.rest_count == 0
    assert r.high_load_count == 0
    assert "normal" in r.summary_advice.lower()
    assert r.marathon_window is False


def test_high_load_marathon_triggers_rest():
    """Yüksek yüklü oyuncu + maraton (4 maç 14 gün) → dinlendir."""
    players = [
        _p(1, 28, [90, 90, 85, 90], fixtures=4),  # avg ~88 yüksek
        _p(2, 24, [60, 65, 70, 55], fixtures=4),
    ]
    r = compute_minutes_management(players).value
    assert r.marathon_window is True
    assert r.high_load_count == 1
    assert r.rest_count == 1
    rec1 = next(x for x in r.recommendations if x.player_external_id == 1)
    assert rec1.rest_advised_next_match is True
    assert rec1.load_band == "yüksek"
    # Yüksek + maraton → 45 hedef
    assert rec1.target_minutes_next_match == 45


def test_veteran_minus_15_target():
    """33 yaş + normal yük → hedef 75 (90 - 15)."""
    players = [_p(1, 33, [60, 60, 60, 60], fixtures=2)]
    r = compute_minutes_management(players).value
    rec = r.recommendations[0]
    assert rec.target_minutes_next_match == 75
    assert any("yaş 33" in f for f in rec.risk_flags)


def test_very_young_capped_at_75():
    players = [_p(1, 17, [60, 60, 60, 60], fixtures=2)]
    r = compute_minutes_management(players).value
    rec = r.recommendations[0]
    assert rec.target_minutes_next_match == 75
    assert any("yaş 17" in f for f in rec.risk_flags)


def test_recent_injury_caps_at_60():
    """Sakatlık dönüşü ≤4 hafta → max 60 dk."""
    players = [_p(1, 25, [40, 50, 60, 60], injured_days=10, fixtures=2)]
    r = compute_minutes_management(players).value
    rec = r.recommendations[0]
    assert rec.target_minutes_next_match == 60
    assert any("sakatlık dönüşü" in f for f in rec.risk_flags)


def test_critical_load_emergency_30():
    """Avg 105 dk/hafta × 4 hafta → kritik → 30 dk öneri."""
    players = [_p(1, 26, [120, 95, 115, 100])]
    r = compute_minutes_management(players).value
    rec = r.recommendations[0]
    assert rec.load_band == "kritik"
    assert rec.target_minutes_next_match == 30


def test_empty_players_returns_zero():
    r = compute_minutes_management([]).value
    assert r.total_players == 0
    assert "boş" in r.summary_advice.lower()


def test_audit_complete():
    res = compute_minutes_management([_p(1, 25, [60, 60, 60])])
    a = res.audit.value
    assert "total_players" in a
    assert "rest_count" in a
    assert "summary_advice" in a
