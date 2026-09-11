"""Spor bilimi: workload (ACWR) + SWC/bireysel baseline (saf)."""
from __future__ import annotations

from app.engine.performance_test import (
    RETEST_MIN_BASELINE,
    TARGET_MAX_HORIZON,
    assess_change,
    assess_target,
    retest_outcome,
    smallest_worthwhile_change,
)
from app.engine.workload import compute_workload

# --------------------------------------------------------------------------- #
# ACWR / workload
# --------------------------------------------------------------------------- #


def test_acwr_sweet_spot():
    # 28 gün sabit yük → akut ≈ kronik → ACWR ~1.0 ideal
    r = compute_workload([500.0] * 28)
    assert r.acwr is not None
    assert 0.9 <= r.acwr <= 1.1
    assert r.risk_zone == "ideal"


def test_acwr_spike_high_risk():
    # 21 gün düşük + son 7 gün ani yüksek → ACWR yüksek
    loads = [300.0] * 21 + [900.0] * 7
    r = compute_workload(loads)
    assert r.acwr is not None and r.acwr > 1.5
    assert r.risk_zone == "yüksek_risk"
    assert any("sakatlık riski" in f for f in r.flags)


def test_acwr_undertraining():
    loads = [600.0] * 21 + [200.0] * 7
    r = compute_workload(loads)
    assert r.risk_zone == "yetersiz"


def test_workload_insufficient_data():
    r = compute_workload([400.0] * 3)
    assert r.acwr is None
    assert r.risk_zone == "bilinmiyor"


def test_monotony_flag_on_uniform_load():
    # Tamamen sabit → sd 0 → monotony None (bölme yok), patlamaz
    r = compute_workload([500.0] * 28)
    assert r.monotony is None


# --------------------------------------------------------------------------- #
# SWC + bireysel baseline
# --------------------------------------------------------------------------- #


def test_swc_is_point2_sd():
    swc = smallest_worthwhile_change([30.0, 32.0, 34.0, 36.0])
    # 0.2 × pstdev
    assert swc > 0


def test_change_below_swc_is_noise():
    # baseline ~35 (SWC≈0.14); 0.1'lik oynama SWC altı → gürültü
    a = assess_change(35.1, [34.0, 35.0, 36.0, 35.0], higher_is_better=True)
    assert a.beyond_swc is False
    assert "değişim yok" in a.verdict


def test_change_above_swc_improvement():
    a = assess_change(42.0, [34.0, 35.0, 36.0, 35.0], higher_is_better=True)
    assert a.beyond_swc is True
    assert a.verdict == "anlamlı gelişme"


def test_retest_outcome_insufficient_below_min_baseline():
    o = retest_outcome(50.0, [34.0, 36.0], higher_is_better=True)
    assert RETEST_MIN_BASELINE == 3
    assert o.category == "insufficient" and o.assessment is None


def test_retest_outcome_categories_follow_direction():
    base = [34.0, 35.0, 36.0, 35.0]
    assert retest_outcome(42.0, base, higher_is_better=True).category == "improved"
    assert retest_outcome(28.0, base, higher_is_better=True).category == "declined"
    assert retest_outcome(35.1, base, higher_is_better=True).category == "unchanged"
    # düşük-iyi protokolde aynı artış gerileme demektir
    assert retest_outcome(42.0, base, higher_is_better=False).category == "declined"


def test_retest_outcome_identical_baseline_is_unchanged_not_claimed():
    # SWC=0 → gürültü tahmini yok → iddia üretme
    o = retest_outcome(40.0, [35.0, 35.0, 35.0], higher_is_better=True)
    assert o.category == "unchanged" and o.assessment is not None and o.assessment.swc == 0.0


def test_target_reached_when_current_meets_target():
    t = assess_target(50.0, [45.0, 48.0, 51.0], higher_is_better=True)
    assert t.status == "reached" and t.tests_to_target == 0 and t.progress_pct == 100.0
    # düşük-iyi: süre hedefin altına indi
    assert assess_target(1.70, [1.80, 1.75, 1.69], higher_is_better=False).status == "reached"


def test_target_on_track_estimates_tests_from_slope():
    # +2/ölçüm eğim, 4 kaldı → 2 ölçüm
    t = assess_target(50.0, [40.0, 42.0, 44.0, 46.0], higher_is_better=True)
    assert t.status == "on_track" and t.tests_to_target == 2 and t.slope == 2.0
    assert t.gap == 4.0 and t.progress_pct == 60.0


def test_target_off_track_when_slope_points_away_or_too_slow():
    away = assess_target(50.0, [46.0, 44.0, 42.0], higher_is_better=True)
    assert away.status == "off_track" and away.tests_to_target is None
    slow = assess_target(50.0, [40.0, 40.1, 40.2], higher_is_better=True)
    assert slow.status == "off_track" and slow.tests_to_target is not None
    assert slow.tests_to_target > TARGET_MAX_HORIZON


def test_target_insufficient_without_enough_points():
    assert assess_target(50.0, [], higher_is_better=True).status == "insufficient"
    t = assess_target(50.0, [40.0, 42.0], higher_is_better=True)
    assert t.status == "insufficient" and t.current == 42.0 and t.gap == 8.0


def test_change_above_swc_decline_lower_better():
    # sprint: süre arttı (kötü) + SWC üstü → anlamlı düşüş
    a = assess_change(4.5, [4.10, 4.12, 4.08, 4.11], higher_is_better=False)
    assert a.beyond_swc is True
    assert "düşüş" in a.verdict
