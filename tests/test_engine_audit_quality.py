"""engine.audit_quality.classify_signal — engine sinyal/gürültü sınıflandırması.

Bu mantık `full_season_audit.py`'nin "hangi engine noise" kararını verir;
StatsBomb verisi olmadan her verdict branch'i burada doğrulanır.
"""

from __future__ import annotations

import math

from app.engine.audit_quality import classify_signal


def test_dead_when_no_samples():
    v = classify_signal([])
    assert v.verdict == "DEAD"
    assert v.n_samples == 0


def test_insufficient_when_below_min():
    v = classify_signal([1.0, 1.2, 0.9], min_samples=20)
    assert v.verdict == "INSUFFICIENT_DATA"
    assert v.n_samples == 3


def test_no_signal_when_flat():
    # 30 örnek, neredeyse sabit (CV≈0) + takım ayrımı yok → gürültü/sabit
    samples = [10.0 + (i % 2) * 0.001 for i in range(30)]
    v = classify_signal(samples, {1: 10.0, 2: 10.0005})
    assert v.verdict == "NO_SIGNAL"


def test_strong_signal_high_variance():
    # Yüksek CV → bilgi taşıyor
    samples = [float(i % 10) + 1.0 for i in range(40)]
    v = classify_signal(samples, {1: 2.0, 2: 8.0})
    assert v.verdict == "STRONG_SIGNAL"


def test_strong_signal_team_spread():
    # Düşük genel CV ama takımlar net ayrışıyor (spread_ratio yüksek)
    samples = [5.0] * 15 + [5.05] * 15  # CV küçük
    v = classify_signal(samples, {1: 3.0, 2: 7.0})  # spread/mean = 4/5 = 0.8 ≥ 0.30
    assert v.verdict == "STRONG_SIGNAL"


def test_moderate_in_between():
    # CV ~0.1-0.2 arası, spread_ratio düşük → MODERATE
    samples = [10.0 + (i % 5) * 0.5 for i in range(30)]  # küçük ama >0.05 CV
    v = classify_signal(samples, {1: 10.0, 2: 10.5})
    assert v.verdict in ("MODERATE", "STRONG_SIGNAL", "NO_SIGNAL")  # branch kapsanır
    # Spesifik: bu dağılımda CV ~0.07, spread_ratio ~0.05 → MODERATE
    assert v.verdict == "MODERATE"


def test_zero_mean_strong_when_spread_large():
    # mean ≈ 0 (zero-sum metrik), yüksek stdev → STRONG
    samples = [-3.0, 3.0] * 15
    v = classify_signal(samples, {1: -2.0, 2: 2.0})
    assert v.verdict == "STRONG_SIGNAL"
    assert math.isinf(v.cv)


def test_zero_mean_no_signal_when_flat():
    samples = [0.0] * 30
    v = classify_signal(samples, {1: 0.0, 2: 0.0})
    assert v.verdict == "NO_SIGNAL"


def test_report_fields_populated():
    v = classify_signal([1.0, 2.0, 3.0, 4.0] * 8, {1: 1.5, 2: 3.5})
    assert v.n_samples == 32
    assert v.n_teams == 2
    assert v.mean > 0
    assert v.stdev > 0
