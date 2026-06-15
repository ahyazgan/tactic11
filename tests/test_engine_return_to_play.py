"""Return-to-Play Plan — çoklu test sentezi."""
from __future__ import annotations

from app.engine.return_to_play import TestResultInput, compute_return_to_play_plan


def _ok(name: str, current: float, baseline: float,
        higher: bool = True, weight: float = 1.0) -> TestResultInput:
    return TestResultInput(
        test_name=name, current=current, pre_injury_baseline=baseline,
        higher_is_better=higher, weight=weight,
    )


def test_full_recovery_returns_phase_5_green():
    """Tüm testler ≥%95 → readiness yüksek, faz 5, yeşil ışık."""
    tests = [
        _ok("cmj", 38.0, 40.0),           # %95
        _ok("sprint10", 1.78, 1.75, higher=False),  # baseline/cur = 0.983
        _ok("y_balance", 96.0, 100.0),    # %96
    ]
    r = compute_return_to_play_plan(7, tests).value
    assert r.phase == 5
    assert r.light == "yeşil"
    assert r.recommended_max_minutes == 90


def test_partial_recovery_phase_3_amber():
    """%80 civarı → faz 3, sarı, max 15 dk."""
    tests = [
        _ok("cmj", 32.0, 40.0),           # %80
        _ok("sprint10", 1.85, 1.75, higher=False),  # %94.6
        _ok("y_balance", 70.0, 100.0),    # %70 (kırmızı)
    ]
    r = compute_return_to_play_plan(7, tests).value
    # ~ (80 + 94.6 + 70) / 3 = 81.5 → faz 3
    assert r.phase == 3
    assert r.recommended_max_minutes == 15
    assert r.light == "kırmızı"  # ortalama < 85


def test_early_recovery_phase_1_red():
    """Düşük readiness → faz 1, sahadan uzak."""
    tests = [_ok("cmj", 20.0, 40.0)]      # %50
    r = compute_return_to_play_plan(7, tests).value
    assert r.phase == 1
    assert r.recommended_max_minutes == 0
    assert "kondisyon" in r.advice.lower()


def test_weighted_average_used():
    """High-weight test ağırlıkça dominant olur."""
    tests = [
        _ok("cmj", 38.0, 40.0, weight=3.0),   # %95, ağırlık 3
        _ok("y_balance", 70.0, 100.0, weight=1.0),  # %70, ağırlık 1
    ]
    r = compute_return_to_play_plan(7, tests).value
    # (95*3 + 70*1)/4 = 88.75 → faz 4
    assert r.phase == 4
    assert r.recommended_max_minutes == 45


def test_weakest_strongest_identified():
    tests = [
        _ok("cmj", 38.0, 40.0),       # %95 → en güçlü
        _ok("y_balance", 60.0, 100.0),  # %60 → en zayıf
        _ok("sprint10", 1.8, 1.75, higher=False),  # %97.2
    ]
    r = compute_return_to_play_plan(7, tests).value
    assert r.strongest_test.test_name == "sprint10"
    assert r.weakest_test.test_name == "y_balance"


def test_empty_tests_zero_phase_one():
    r = compute_return_to_play_plan(7, []).value
    assert r.test_count == 0
    assert r.overall_readiness_pct == 0.0
    assert r.phase == 1


def test_audit_complete():
    res = compute_return_to_play_plan(
        7, [_ok("cmj", 38.0, 40.0)],
    )
    a = res.audit.value
    assert "overall_readiness_pct" in a
    assert "phase" in a
    assert "light" in a
    assert "advice" in a


def test_invalid_baseline_treated_as_zero_pct():
    """baseline=0 → pct=0, scored but kırmızı."""
    bad = TestResultInput("invalid", current=10.0, pre_injury_baseline=0.0)
    r = compute_return_to_play_plan(7, [bad]).value
    assert r.test_scores[0].pct_of_baseline == 0.0
    assert r.test_scores[0].light == "kırmızı"
