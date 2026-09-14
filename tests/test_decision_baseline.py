"""engine.decision_baseline — durum-taban cetveli (karar etkisi v2).

Kilitlenen davranış: (1) düzeltme hücre ortalamasını çıkarır, (2) küçük ya da
görülmemiş hücre genel ortalamaya düşer (gürültü öğretmez), (3) bant sınırları
ve skor durumu sabit.
"""
from __future__ import annotations

from app.engine.decision_baseline import (
    MIN_CELL_N,
    BaselineSample,
    adjusted_delta,
    fit_state_baseline,
    minute_band,
    score_state,
)


def test_minute_bands_and_score_state() -> None:
    assert [minute_band(m) for m in (0.0, 44.9, 45.0, 59.9, 60.0, 70.0, 79.9, 80.0, 95.0)] == \
        [0, 0, 1, 1, 2, 3, 3, 4, 4]
    assert score_state(1, 0) == "leading" and score_state(0, 0) == "drawing"
    assert score_state(0, 2) == "trailing"


def _cell(minute: float, state: str, values: list[float]) -> list[BaselineSample]:
    return [BaselineSample(minute, state, v) for v in values]


def test_adjusted_delta_subtracts_cell_mean() -> None:
    # 75' önde: olağan akış -0.02/dk (öndeki takım çekilir); 45' berabere: +0.01
    base = fit_state_baseline(
        _cell(75.0, "leading", [-0.02] * MIN_CELL_N) + _cell(50.0, "drawing", [0.01] * MIN_CELL_N)
    )
    # Gözlenen -0.005: v1 "nötr" derdi; duruma göre +0.015 → olumlu yönde
    assert adjusted_delta(base, minute=76.0, score_state="leading", xg_delta=-0.005) == 0.015
    assert adjusted_delta(base, minute=55.0, score_state="drawing", xg_delta=0.01) == 0.0


def test_small_or_unseen_cell_falls_back_to_global_mean() -> None:
    base = fit_state_baseline(
        _cell(75.0, "leading", [-0.02] * MIN_CELL_N) + _cell(30.0, "trailing", [0.04] * 2)
    )
    n = MIN_CELL_N + 2
    assert base.global_mean == round((-0.02 * MIN_CELL_N + 0.08) / n, 5)
    # küçük hücre (n=2) → genel ortalama
    assert base.expected(30.0, "trailing") == base.global_mean
    # görülmemiş hücre → genel ortalama
    assert base.expected(85.0, "drawing") == base.global_mean
    # dolu hücre → kendi ortalaması
    assert base.expected(72.0, "leading") == -0.02


def test_empty_baseline_is_zero() -> None:
    base = fit_state_baseline([])
    assert base.samples == 0 and base.global_mean == 0.0
    assert adjusted_delta(base, minute=60.0, score_state="drawing", xg_delta=0.03) == 0.03
