"""Tahmin backtest harness — walk-forward + v3 vs baseline + kalibrasyon."""

from __future__ import annotations

from app.engine.backtest import MatchRow, run_backtest


def _double_round_robin_home_wins(n_teams: int = 8) -> list[MatchRow]:
    """Çift devreli lig; HER maçta ev sahibi 2-1 kazanır.

    Ev sahibi avantajı GERÇEK ama takım güçleri simetrik. Baseline (hfa=1)
    bunu yakalayamaz (simetrik tahmin); v3 (hfa=1.15) ev sahibine eğilir →
    daha düşük log-loss. Kontrollü kazanç testi.
    """
    teams = [f"T{i}" for i in range(n_teams)]
    rows: list[MatchRow] = []
    day = 0
    for home in teams:
        for away in teams:
            if home == away:
                continue
            day += 1
            rows.append(MatchRow(
                date=f"2024-{1 + day // 28:02d}-{1 + day % 28:02d}",
                home=home, away=away, hg=2, ag=1,
            ))
    return rows


def test_harness_produces_valid_metrics():
    cmp = run_backtest(_double_round_robin_home_wins(), warmup=2)
    for m in (cmp.baseline, cmp.v3):
        assert m.n > 0
        assert m.brier > 0.0
        assert m.log_loss > 0.0
        assert 0.0 <= m.accuracy <= 1.0
        assert 0.0 <= m.ece <= 1.0
    assert cmp.baseline.n == cmp.v3.n


def test_v3_beats_baseline_when_home_advantage_real():
    """Ev sahibi gerçekten kazanırken v3 (hfa) baseline'dan iyi olmalı."""
    cmp = run_backtest(_double_round_robin_home_wins(), warmup=2)
    # Gerçek sonuç hep 'home' → v3 ev sahibine daha çok olasılık verir.
    assert cmp.v3.log_loss < cmp.baseline.log_loss
    assert cmp.v3.accuracy >= cmp.baseline.accuracy


def test_harness_reports_calibration_delta():
    cmp = run_backtest(_double_round_robin_home_wins(n_teams=10), warmup=2)
    assert cmp.calibration is not None
    assert cmp.calibration.temperature > 0.0
    assert cmp.calibration.n_test > 0
    # Kalibrasyon test setinde log-loss'u kötüleştirmemeli (küçük tolerans).
    assert cmp.calibration.log_loss_calibrated <= cmp.calibration.log_loss_raw + 0.02


def test_harness_warmup_excludes_early_matches():
    """warmup yüksekse erken maçlar örnekleme girmez (sızıntısız form)."""
    rows = _double_round_robin_home_wins(n_teams=6)
    low = run_backtest(rows, warmup=2)
    high = run_backtest(rows, warmup=8)
    assert high.v3.n < low.v3.n
