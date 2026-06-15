"""Opportunity Window Detector testleri."""
from __future__ import annotations

from app.engine.opportunity_window import (
    TacticalSnapshot,
    compute_opportunity_windows,
)


def _snap(minute: float, **kwargs) -> TacticalSnapshot:
    base = dict(
        our_press_intensity=0.5,
        opp_press_intensity=0.5,
        opp_distance_covered=0.7,
        opp_sub_count_used=0,
        opp_yellow_count=0,
        opp_red_imminent=False,
        our_xg_recent_5min=0.0,
        opp_xg_recent_5min=0.0,
    )
    base.update(kwargs)
    return TacticalSnapshot(minute=minute, **base)


def test_no_signal_returns_empty():
    r = compute_opportunity_windows([_snap(30), _snap(45), _snap(60)]).value
    assert len(r.windows) == 0
    assert "açık bir opportunity" in r.summary


def test_fatigue_window_detected_when_distance_drops():
    snaps = [
        _snap(45, opp_distance_covered=0.85),
        _snap(60, opp_distance_covered=0.65),  # 0.20 drop > 0.12 threshold
    ]
    r = compute_opportunity_windows(snaps).value
    fatigue = [w for w in r.windows if w.type == "opp_fatigued"]
    assert fatigue
    assert "yorgunluk" in fatigue[0].why.lower()


def test_press_drop_window():
    snaps = [
        _snap(50, opp_press_intensity=0.80),
        _snap(65, opp_press_intensity=0.45),  # 0.35 drop > 0.20 threshold
    ]
    r = compute_opportunity_windows(snaps).value
    press = [w for w in r.windows if w.type == "opp_press_drop"]
    assert press
    assert press[0].confidence >= 0.5


def test_momentum_ours_detected_high_xg_gap():
    snaps = [_snap(75, our_xg_recent_5min=0.40, opp_xg_recent_5min=0.05)]
    r = compute_opportunity_windows(snaps).value
    mom = [w for w in r.windows if w.type == "momentum_ours"]
    assert mom
    assert mom[0].confidence > 0.0


def test_card_pressure_window():
    snaps = [_snap(60, opp_yellow_count=3)]
    r = compute_opportunity_windows(snaps).value
    cards = [w for w in r.windows if w.type == "opp_card_pressure"]
    assert cards
    assert "sarı" in cards[0].why.lower() or "kırmızı" in cards[0].why.lower()


def test_red_imminent_higher_confidence():
    snaps = [_snap(60, opp_yellow_count=2, opp_red_imminent=True)]
    r = compute_opportunity_windows(snaps).value
    cards = [w for w in r.windows if w.type == "opp_card_pressure"]
    assert cards
    assert cards[0].confidence >= 0.85


def test_subs_exhausted_window():
    snaps = [_snap(70, opp_sub_count_used=4)]
    r = compute_opportunity_windows(snaps).value
    subs = [w for w in r.windows if w.type == "opp_subs_exhausted"]
    assert subs
    assert subs[0].confidence >= 0.7


def test_disorganized_multi_signal():
    snaps = [
        _snap(50, opp_distance_covered=0.85, opp_press_intensity=0.75),
        _snap(60, opp_distance_covered=0.75, opp_press_intensity=0.62),
        _snap(70, opp_distance_covered=0.66, opp_press_intensity=0.50),
    ]
    r = compute_opportunity_windows(snaps).value
    types = {w.type for w in r.windows}
    # En az fatigue + press_drop tespit edilmeli; disorganized de patlayabilir
    assert "opp_fatigued" in types or "opp_press_drop" in types or "opp_disorganized" in types


def test_dedupe_close_minute_same_type():
    """Aynı tip, < 6 dk arayla iki pencere → tek pencere (yüksek conf kalır)."""
    snaps = [
        _snap(60, opp_yellow_count=3),
        _snap(63, opp_yellow_count=4),
    ]
    r = compute_opportunity_windows(snaps).value
    cards = [w for w in r.windows if w.type == "opp_card_pressure"]
    assert len(cards) == 1  # dedupe


def test_empty_snapshots():
    r = compute_opportunity_windows([]).value
    assert r.snapshot_count == 0
    assert len(r.windows) == 0


def test_audit_complete():
    snaps = [_snap(60, opp_yellow_count=3)]
    res = compute_opportunity_windows(snaps)
    a = res.audit.value
    assert "snapshot_count" in a
    assert "window_count" in a
    assert "types" in a
    assert "top_confidence" in a


def test_summary_mentions_top_window():
    snaps = [_snap(60, opp_yellow_count=3)]
    r = compute_opportunity_windows(snaps).value
    assert "opp_card_pressure" in r.summary or "pencere" in r.summary.lower()
