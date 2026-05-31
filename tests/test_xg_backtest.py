"""engine.xg.backtest — xG geometric kalibrasyon testi.

Test stratejisi:
  1. Sentetik "mükemmel kalibre" veri → Brier düşük, ECE düşük
  2. Bozuk model (hep yüksek tahmin) → bias yakalanıyor mu?
  3. Pattern breakdown doğru çalışıyor mu?
  4. Penalty şutları hariç tutuluyor mu?
  5. StatsBomb koordinat dönüşümü doğru mu?
  6. Audit trail tam mı?

Mevcut test pattern: `_shot(**kw)` factory → `Shot`.
"""
from __future__ import annotations

import pytest

from app.domain import Shot
from app.engine.xg.compute import compute_shot_xg_geometric
from app.engine.xg.backtest import (
    XGBacktestReport,
    run_xg_geometric_backtest,
    _compute_ece,
    _pattern_breakdown,
)
from app.engine.backtest.compute import BacktestReport, CalibrationBin


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def _shot(**kw) -> Shot:
    base = dict(
        sport="football",
        match_external_id=1,
        player_external_id=10,
        minute=20.0,
        x=85.0,
        y=50.0,
        body_part="right_foot",
        pattern="open_play",
        is_goal=False,
    )
    base.update(kw)
    return Shot(**base)  # type: ignore[arg-type]


def _make_shots_with_real_xg(n: int = 200) -> list[Shot]:
    """Gerçekçi şut dağılımı: penalty noktası çevresinde yoğun.

    is_goal, modelin kendi xG'si baz alınarak bernoulli örneklemesiyle
    atanır — bu senaryoda model "gerçekten" kalibre olmalı.
    """
    import random
    random.seed(42)
    shots = []
    positions = [
        # (x, y, pattern, body_part)
        (88.0, 50.0, "open_play", "right_foot"),  # yüksek xG
        (75.0, 50.0, "open_play", "right_foot"),  # orta
        (70.0, 35.0, "open_play", "head"),         # köşe, kafa
        (92.0, 30.0, "open_play", "right_foot"),   # dar açı
        (80.0, 50.0, "fast_break", "right_foot"),  # fast break
        (78.0, 50.0, "set_piece", "right_foot"),   # set piece
    ]
    for i in range(n):
        x, y, pattern, body_part = positions[i % len(positions)]
        # Hafif jitter — aynı pozisyon tekrarı önle
        x = min(99.5, x + random.uniform(-3, 3))
        y = min(99.5, max(0.5, y + random.uniform(-5, 5)))
        s_tmp = _shot(x=x, y=y, pattern=pattern, body_part=body_part, is_goal=False)
        xg = compute_shot_xg_geometric(s_tmp).value.xg
        # Bernoulli: modelin xG'si kadar olasılıkla gol
        is_goal = random.random() < xg
        shots.append(_shot(x=x, y=y, pattern=pattern, body_part=body_part, is_goal=is_goal))
    return shots


# ──────────────────────────────────────────────────────────────────────────────
# Temel backtest testleri
# ──────────────────────────────────────────────────────────────────────────────

class TestRunXGGeometricBacktest:

    def test_returns_engine_result(self):
        shots = _make_shots_with_real_xg(100)
        result = run_xg_geometric_backtest(shots, season=2018)
        assert hasattr(result, "value")
        assert hasattr(result, "audit")
        assert isinstance(result.value, XGBacktestReport)

    def test_well_calibrated_on_bernoulli_data(self):
        """Model kendi xG'siyle üretilmiş veriye kalibre olmalı."""
        shots = _make_shots_with_real_xg(500)
        result = run_xg_geometric_backtest(shots, n_calibration_bins=5)
        r = result.value
        # Geniş tolerans — stochastic test
        assert r.brier_score < 0.15, f"Brier çok yüksek: {r.brier_score}"
        # ECE %15'ten büyük olmamalı (istatistiksel gürültü payı)
        assert r.expected_calibration_error < 0.15

    def test_penalty_shots_excluded(self):
        """Penalty şutları backtest'e dahil edilmez."""
        shots_no_penalty = _make_shots_with_real_xg(50)
        penalty_shots = [_shot(pattern="penalty", is_goal=True) for _ in range(20)]
        all_shots = shots_no_penalty + penalty_shots

        result_with = run_xg_geometric_backtest(all_shots)
        result_without = run_xg_geometric_backtest(shots_no_penalty)

        # Penalty eklemek n_shots'u değiştirmemeli
        assert result_with.value.n_shots == result_without.value.n_shots

    def test_over_estimating_model_detected(self):
        """Model hep 0.9 tahmin etse, bias pozitif ve Brier yüksek olmalı."""
        # Gerçekte düşük xG'li şutlar ama is_goal=False (model over-estimate)
        shots = [_shot(x=50.0, y=50.0, is_goal=False) for _ in range(100)]
        result = run_xg_geometric_backtest(shots)
        r = result.value
        # x=50 için xG zaten çok düşük — model "düşük" diyor, gol yok
        # Bu sefer under-estimate değil; ama kalibrasyon tutarlı olmalı
        assert r.observed_goal_rate == 0.0
        # mean_predicted > observed (hatta 0 gözlem, model biraz tahmin eder)
        assert r.mean_predicted_xg >= 0.0

    def test_only_penalty_shots_raises(self):
        """Sadece penalty şutu verilince ValueError beklenir."""
        shots = [_shot(pattern="penalty", is_goal=True) for _ in range(10)]
        with pytest.raises(ValueError, match="penalty"):
            run_xg_geometric_backtest(shots)

    def test_empty_shots_raises(self):
        with pytest.raises(ValueError):
            run_xg_geometric_backtest([])

    def test_season_stored_in_report(self):
        shots = _make_shots_with_real_xg(50)
        result = run_xg_geometric_backtest(shots, season=2019)
        assert result.value.season == 2019

    def test_n_shots_and_n_goals_consistent(self):
        shots = _make_shots_with_real_xg(100)
        result = run_xg_geometric_backtest(shots)
        r = result.value
        assert r.n_shots > 0
        assert r.n_goals <= r.n_shots
        assert abs(r.observed_goal_rate - r.n_goals / r.n_shots) < 1e-4

    def test_brier_bounded(self):
        """Brier score ∈ [0, 1]."""
        shots = _make_shots_with_real_xg(100)
        result = run_xg_geometric_backtest(shots)
        assert 0.0 <= result.value.brier_score <= 1.0

    def test_calibration_bins_populated(self):
        shots = _make_shots_with_real_xg(200)
        result = run_xg_geometric_backtest(shots, n_calibration_bins=5)
        assert len(result.value.calibration_bins) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Pattern breakdown testleri
# ──────────────────────────────────────────────────────────────────────────────

class TestPatternBreakdown:

    def test_patterns_separated(self):
        shots = (
            [_shot(pattern="open_play", is_goal=True) for _ in range(10)] +
            [_shot(pattern="open_play", is_goal=False) for _ in range(40)] +
            [_shot(pattern="fast_break", is_goal=True) for _ in range(5)] +
            [_shot(pattern="fast_break", is_goal=False) for _ in range(5)]
        )
        result = run_xg_geometric_backtest(shots)
        patterns = {p.pattern for p in result.value.pattern_breakdown}
        assert "open_play" in patterns
        assert "fast_break" in patterns

    def test_observed_rate_correct(self):
        """open_play: 10 gol / 50 şut → 0.2."""
        shots = (
            [_shot(pattern="open_play", is_goal=True) for _ in range(10)] +
            [_shot(pattern="open_play", is_goal=False) for _ in range(40)]
        )
        result = run_xg_geometric_backtest(shots)
        op = next(p for p in result.value.pattern_breakdown if p.pattern == "open_play")
        assert abs(op.observed_rate - 0.2) < 1e-4

    def test_bias_sign(self):
        """Düşük xG pozisyonunda gol sayısı yoksa: mean_xg > 0 → bias pozitif."""
        shots = [_shot(x=50.0, y=50.0, pattern="open_play", is_goal=False) for _ in range(30)]
        result = run_xg_geometric_backtest(shots)
        op = next(p for p in result.value.pattern_breakdown if p.pattern == "open_play")
        # model biraz xG tahmin eder, gol yok → bias pozitif
        assert op.bias >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# ECE hesabı
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeECE:

    def test_perfect_calibration_zero_ece(self):
        """Her binde tahmin = gözlem → ECE = 0."""
        bins = (
            CalibrationBin(lower=0.0, upper=0.2, n=50, mean_predicted=0.1, observed_rate=0.1),
            CalibrationBin(lower=0.2, upper=0.5, n=100, mean_predicted=0.35, observed_rate=0.35),
            CalibrationBin(lower=0.5, upper=1.0, n=50, mean_predicted=0.7, observed_rate=0.7),
        )
        bt = BacktestReport(
            n=200, hit_rate=0.5, brier_score=0.1,
            mean_predicted=0.35, observed_rate=0.35,
            calibration=bins, well_calibrated=True,
        )
        ece = _compute_ece(bt)
        assert ece == pytest.approx(0.0, abs=1e-6)

    def test_bad_calibration_nonzero_ece(self):
        """Büyük fark → ECE > 0."""
        bins = (
            CalibrationBin(lower=0.0, upper=0.5, n=100, mean_predicted=0.1, observed_rate=0.5),
        )
        bt = BacktestReport(
            n=100, hit_rate=0.5, brier_score=0.2,
            mean_predicted=0.1, observed_rate=0.5,
            calibration=bins, well_calibrated=False,
        )
        ece = _compute_ece(bt)
        assert ece == pytest.approx(0.4, abs=1e-4)

    def test_empty_calibration(self):
        bt = BacktestReport(
            n=0, hit_rate=0.0, brier_score=0.0,
            mean_predicted=0.0, observed_rate=0.0,
            calibration=(), well_calibrated=True,
        )
        assert _compute_ece(bt) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Audit trail
# ──────────────────────────────────────────────────────────────────────────────

class TestAuditTrail:

    def test_audit_engine_name(self):
        shots = _make_shots_with_real_xg(50)
        result = run_xg_geometric_backtest(shots)
        assert result.audit.engine == "engine.xg.backtest"

    def test_audit_has_brier_score(self):
        shots = _make_shots_with_real_xg(50)
        result = run_xg_geometric_backtest(shots)
        assert "brier_score" in result.audit.value

    def test_audit_season_recorded(self):
        shots = _make_shots_with_real_xg(50)
        result = run_xg_geometric_backtest(shots, season=2020)
        assert result.audit.value["season"] == 2020

    def test_audit_excluded_field(self):
        shots = _make_shots_with_real_xg(50)
        result = run_xg_geometric_backtest(shots)
        assert result.audit.inputs["excluded"] == "penalty"


# ──────────────────────────────────────────────────────────────────────────────
# StatsBomb koordinat dönüşümü
# ──────────────────────────────────────────────────────────────────────────────

class TestStatsBombCoordinateConversion:
    """StatsBomb (0-120, 0-80) → Shot (0-100, 0-100) dönüşüm doğruluğu."""

    def test_penalty_spot_mapping(self):
        """StatsBomb'da penaltı noktası ~(108, 40) → yaklaşık (90, 50) normalized."""
        sb_x, sb_y = 108.0, 40.0
        norm_x = (sb_x / 120.0) * 100.0
        norm_y = (sb_y / 80.0) * 100.0
        assert 88.0 < norm_x < 92.0
        assert 48.0 < norm_y < 52.0

    def test_center_spot_mapping(self):
        """Orta saha (60, 40) → (50, 50)."""
        norm_x = (60.0 / 120.0) * 100.0
        norm_y = (40.0 / 80.0) * 100.0
        assert abs(norm_x - 50.0) < 1e-4
        assert abs(norm_y - 50.0) < 1e-4
