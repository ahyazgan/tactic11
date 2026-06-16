from __future__ import annotations

import pytest

from app.engine.calibration import (
    apply_temperature,
    compute_calibration,
    fit_temperature,
)


def test_apply_temperature_identity_at_one():
    probs = (0.6, 0.25, 0.15)
    out = apply_temperature(probs, 1.0)
    assert out == pytest.approx(probs, abs=1e-9)


def test_apply_temperature_normalizes():
    out = apply_temperature((0.9, 0.05, 0.05), 2.5)
    assert sum(out) == pytest.approx(1.0, abs=1e-9)


def test_apply_temperature_softens_when_t_gt_one():
    """T>1 → tepe olasılık düşer (aşırı-güven kırılır)."""
    raw = (0.9, 0.05, 0.05)
    softened = apply_temperature(raw, 2.0)
    assert softened[0] < raw[0]
    assert softened[1] > raw[1]  # kütle uca dağılır


def test_apply_temperature_sharpens_when_t_lt_one():
    raw = (0.6, 0.25, 0.15)
    sharper = apply_temperature(raw, 0.5)
    assert sharper[0] > raw[0]


def test_apply_temperature_handles_nonpositive_t():
    probs = (0.5, 0.3, 0.2)
    assert apply_temperature(probs, 0.0) == pytest.approx(probs, abs=1e-9)


def test_fit_temperature_empty_is_identity():
    c = fit_temperature([])
    assert c.temperature == 1.0
    assert c.n_train == 0
    assert c.improved is False


def test_fit_temperature_corrects_overconfidence():
    """Aşırı-güvenli motor (hep %90 home ama gerçek %60) → T>1, log-loss düşer."""
    samples = []
    for i in range(100):
        actual = "home" if i % 10 < 6 else ("draw" if i % 10 < 8 else "away")
        samples.append((0.9, 0.05, 0.05, actual))
    c = fit_temperature(samples)
    assert c.temperature > 1.0  # yumuşatma önerildi
    assert c.log_loss_after < c.log_loss_before
    assert c.improved is True


def test_fit_temperature_well_calibrated_stays_near_identity():
    """Zaten kalibre veri → T≈1, düzeltme zarar vermez."""
    samples = []
    for i in range(100):
        actual = "home" if i % 10 < 6 else ("draw" if i % 10 < 8 else "away")
        samples.append((0.6, 0.2, 0.2, actual))
    c = fit_temperature(samples)
    assert c.temperature == pytest.approx(1.0, abs=0.4)
    assert c.log_loss_after <= c.log_loss_before + 1e-6


def test_compute_calibration_carries_recalibration():
    samples = []
    for i in range(100):
        actual = "home" if i % 10 < 6 else ("draw" if i % 10 < 8 else "away")
        samples.append((0.9, 0.05, 0.05, actual))
    r = compute_calibration(samples).value
    assert r.recommended_temperature is not None
    assert r.recommended_temperature > 1.0
    # Düzeltilmiş log-loss ham log-loss'tan iyi (≤).
    assert r.log_loss_recalibrated is not None
    assert r.log_loss_recalibrated <= r.log_loss
    assert r.ece_recalibrated is not None


def test_compute_calibration_recalibrate_off_leaves_none():
    samples = [(0.9, 0.05, 0.05, "home"), (0.9, 0.05, 0.05, "away")]
    r = compute_calibration(samples, recalibrate=False).value
    assert r.recommended_temperature is None
    assert r.log_loss_recalibrated is None
    assert r.ece_recalibrated is None
    # Ham metrikler yine hesaplanır.
    assert r.log_loss is not None


def test_compute_calibration_empty_has_no_recalibration():
    r = compute_calibration([]).value
    assert r.sample_count == 0
    assert r.recommended_temperature is None
