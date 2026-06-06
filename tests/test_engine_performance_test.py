"""performance_test — spor bilimi test skorlama + yorumlama (saf)."""
from __future__ import annotations

import pytest

from app.engine.performance_test import (
    evaluate_battery,
    interpret_progression,
    score_test,
)

# --------------------------------------------------------------------------- #
# score_test — norm rating (yön'e duyarlı)
# --------------------------------------------------------------------------- #


def test_cmj_high_is_elite():
    s = score_test("cmj", 42.0)   # yüksek sıçrama iyi
    assert s.rating == "elit"


def test_cmj_low_is_weak():
    s = score_test("cmj", 28.0)
    assert s.rating == "zayıf"


def test_sprint_low_time_is_elite():
    s = score_test("sprint_30m", 3.95)  # düşük süre iyi
    assert s.rating == "elit"


def test_sprint_high_time_is_weak():
    s = score_test("sprint_30m", 4.6)
    assert s.rating == "zayıf"


def test_unknown_protocol_raises():
    with pytest.raises(ValueError, match="bilinmeyen protokol"):
        score_test("uçuş_testi", 1.0)


# --------------------------------------------------------------------------- #
# squad percentile (yön'e duyarlı)
# --------------------------------------------------------------------------- #


def test_percentile_higher_better():
    # CMJ 40, kadro [30,32,35,38] hepsinden iyi → %100
    s = score_test("cmj", 40.0, reference_values=[30.0, 32.0, 35.0, 38.0])
    assert s.squad_percentile == 100.0


def test_percentile_lower_better():
    # sprint 4.0s, kadro [4.5,4.3,4.2,4.1] hepsinden hızlı → %100
    s = score_test("sprint_30m", 4.0, reference_values=[4.5, 4.3, 4.2, 4.1])
    assert s.squad_percentile == 100.0


# --------------------------------------------------------------------------- #
# battery
# --------------------------------------------------------------------------- #


def test_battery_flags_weak_and_strong():
    r = evaluate_battery(10, [("cmj", 42.0), ("sprint_30m", 4.6)])
    assert any("Jump" in s for s in r.strong_areas)   # cmj elit
    assert any("Sprint" in s for s in r.weak_areas)    # sprint zayıf


# --------------------------------------------------------------------------- #
# progression — gelişim + regresyon (yön'e duyarlı)
# --------------------------------------------------------------------------- #


def test_progression_improving_higher_better():
    # CMJ sezon boyu artıyor → gelişiyor
    r = interpret_progression("cmj", [34.0, 36.0, 38.0, 40.0])
    assert r.trend == "gelişiyor"


def test_progression_improving_lower_better():
    # sprint süresi düşüyor → gelişiyor (daha hızlı)
    r = interpret_progression("sprint_30m", [4.30, 4.22, 4.15, 4.08])
    assert r.trend == "gelişiyor"


def test_progression_regression_alert():
    # CMJ aniden düşüyor → regresyon uyarısı (sakatlık/yük)
    r = interpret_progression("cmj", [40.0, 41.0, 40.0, 33.0, 32.0, 31.0])
    assert r.regression_alert is True


def test_progression_flat():
    r = interpret_progression("cmj", [38.0, 38.1, 37.9, 38.0])
    assert r.trend == "sabit"
