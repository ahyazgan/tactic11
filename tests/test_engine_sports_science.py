"""Spor bilimi: workload (ACWR) + SWC/bireysel baseline (saf)."""
from __future__ import annotations

from app.engine.performance_test import assess_change, smallest_worthwhile_change
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


def test_change_above_swc_decline_lower_better():
    # sprint: süre arttı (kötü) + SWC üstü → anlamlı düşüş
    a = assess_change(4.5, [4.10, 4.12, 4.08, 4.11], higher_is_better=False)
    assert a.beyond_swc is True
    assert "düşüş" in a.verdict
