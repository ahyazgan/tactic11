"""engine.calibration — Brier score + log loss + ECE tests."""

from __future__ import annotations

import pytest

from app.engine.calibration import compute_calibration


def test_calibration_empty_samples():
    r = compute_calibration([]).value
    assert r.sample_count == 0
    assert r.brier_score is None
    assert r.log_loss is None
    assert r.expected_calibration_error is None
    assert r.home_outcome_buckets == []


def test_calibration_perfect_predictor_brier_zero():
    """Hep doğru tahmin → Brier ≈ 0, log loss küçük."""
    samples = [
        (1.0, 0.0, 0.0, "home"),  # %100 home dedi, home oldu
        (0.0, 1.0, 0.0, "draw"),
        (0.0, 0.0, 1.0, "away"),
    ]
    r = compute_calibration(samples).value
    assert r.sample_count == 3
    assert r.brier_score == pytest.approx(0.0, abs=0.001)
    # Log loss küçük olmalı (clipping yüzünden tam 0 değil)
    assert r.log_loss < 0.001


def test_calibration_worst_predictor_high_brier():
    """Tam ters tahmin → Brier yüksek."""
    samples = [
        (0.0, 0.0, 1.0, "home"),  # %100 away dedi, home oldu
        (1.0, 0.0, 0.0, "away"),
    ]
    r = compute_calibration(samples).value
    # Her örnekte iki one-hot kez 1 fark + bir 0 fark = 2.0 per sample
    assert r.brier_score == pytest.approx(2.0, abs=0.001)
    assert r.log_loss > 5.0  # ln(1e-6) ≈ 13.8


def test_calibration_uniform_predictor():
    """Her zaman 1/3-1/3-1/3 tahmin → Brier = 2/3 ≈ 0.667."""
    samples = [
        (1/3, 1/3, 1/3, "home"),
        (1/3, 1/3, 1/3, "draw"),
        (1/3, 1/3, 1/3, "away"),
    ]
    r = compute_calibration(samples).value
    # Brier per sample: (1/3-y_home)² + (1/3-y_draw)² + (1/3-y_away)²
    # Eğer y_home=1: (1/3-1)² + (1/3)² + (1/3)² = 4/9 + 1/9 + 1/9 = 6/9
    # Hep aynı → 6/9 ≈ 0.667
    assert r.brier_score == pytest.approx(0.667, abs=0.01)


def test_calibration_buckets_count_10():
    """10 bucket [0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]."""
    samples = [(p / 10, 1/3, 1.0 - p / 10 - 1/3, "home") for p in range(10)]
    r = compute_calibration(samples).value
    assert len(r.home_outcome_buckets) == 10
    # İlk bucket [0, 0.1) prob ~0; son bucket [0.9, 1.0] prob ~0.9
    assert r.home_outcome_buckets[0].bucket_lower == 0.0
    assert r.home_outcome_buckets[-1].bucket_upper == 1.0


def test_calibration_ece_zero_when_perfectly_calibrated():
    """Bir bucket'ta avg(pred)=0.7, gerçek frekans 0.7 → o bucket sıfır katkı."""
    # Bucket [0.7, 0.8): 10 örnek, ortalama 0.7, gerçek 7/10 = 0.7
    samples = []
    for i in range(10):
        is_home = i < 7  # 7'si home
        samples.append((0.7, 0.15, 0.15, "home" if is_home else "away"))
    r = compute_calibration(samples).value
    assert r.expected_calibration_error == pytest.approx(0.0, abs=0.001)


def test_calibration_audit_engine_name():
    r = compute_calibration([(0.5, 0.3, 0.2, "home")])
    assert r.audit.engine == "engine.calibration"
    assert r.audit.engine_version == "1"
    assert "Brier" in r.audit.formula
