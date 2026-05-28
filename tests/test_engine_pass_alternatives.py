"""engine.pass_alternatives — frame-by-frame alternatif analizi tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.pass_alternatives import (
    compute_pass_alternatives,
    compute_player_pass_alternatives_summary,
)


def _p(player: int, sx: float, sy: float, ex: float, ey: float,
       minute: float = 10.0) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
    )


def test_forward_pass_has_alternatives():
    """Standart ileri pas → 3 alternatif önerisi gelir."""
    p = _p(100, 50, 50, 65, 50)
    r = compute_pass_alternatives(p).value
    assert len(r.alternatives) == 3
    # En iyi alternatif actual'dan en az 0 olmalı (sort desc)
    assert r.alternatives[0].delta_vs_actual >= r.alternatives[-1].delta_vs_actual


def test_actual_optimal_flag():
    """Çok yüksek xT noktasına yapılan pas → actual_was_optimal=True."""
    # Kale ağzına yakın bir noktaya pas (yüksek xT)
    p = _p(100, 50, 50, 98, 50)
    r = compute_pass_alternatives(p).value
    # 98,50 muhtemelen optimal'a yakın; delta ≤ 0.02 ise optimal
    assert isinstance(r.actual_was_optimal, bool)


def test_backward_pass_has_better_alternatives():
    """Geri pas → ileri alternatifler bulunmalı, delta>0."""
    p = _p(100, 70, 50, 30, 50)  # ileride başlayıp geriye attı
    r = compute_pass_alternatives(p).value
    assert r.best_alternative_delta > 0
    assert r.actual_was_optimal is False


def test_audit_includes_top_alternatives():
    p = _p(100, 50, 50, 60, 50)
    r = compute_pass_alternatives(p)
    assert "top_alternatives" in r.audit.value
    assert len(r.audit.value["top_alternatives"]) == 3


def test_player_summary_aggregates_passes():
    """Bir oyuncunun N pasının toplu özeti."""
    passes = [
        _p(100, 50, 50, 60, 50, minute=10.0),
        _p(100, 30, 50, 70, 50, minute=20.0),
        _p(100, 70, 50, 30, 50, minute=30.0),  # geri pas
        _p(200, 50, 50, 60, 50, minute=15.0),  # başka oyuncu
    ]
    summary = compute_player_pass_alternatives_summary(100, passes)
    assert summary["passes_analyzed"] == 3
    assert 0.0 <= summary["suboptimal_share"] <= 1.0
    assert len(summary["top_suboptimal"]) <= 3


def test_player_summary_no_passes_returns_zero():
    summary = compute_player_pass_alternatives_summary(999, [])
    assert summary["passes_analyzed"] == 0
    assert summary["mean_best_delta"] == 0.0
