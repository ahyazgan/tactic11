"""A what_if + B backtest — saf zeka engine'leri."""
from __future__ import annotations

from app.engine.backtest import backtest
from app.engine.what_if import (
    PlayerContribution,
    rank_removals,
    simulate_removal,
)

# --------------------------------------------------------------------------- #
# A — what_if
# --------------------------------------------------------------------------- #


def _contribs() -> list[PlayerContribution]:
    return [
        PlayerContribution(10, 0.5),   # yıldız
        PlayerContribution(8, 0.3),
        PlayerContribution(4, 0.2),
    ]


def test_removing_star_drops_metric():
    r = simulate_removal(
        baseline_team_metric=1.0, contributions=_contribs(),
        remove_player_id=10,
    )
    assert r.delta < 0
    assert r.projected_metric < r.baseline_metric


def test_replacement_can_offset():
    r = simulate_removal(
        baseline_team_metric=1.0, contributions=_contribs(),
        remove_player_id=4, replacement_contribution=0.5,
    )
    assert r.delta > 0  # yedek (0.5) çıkandan (0.2) verimli


def test_unknown_player_only_replacement_effect():
    r = simulate_removal(
        baseline_team_metric=1.0, contributions=_contribs(),
        remove_player_id=999, replacement_contribution=0.1,
    )
    assert r.delta == 0.1
    assert "listesinde yok" in r.note


def test_rank_removals_orders_safest_and_costly():
    rk = rank_removals(baseline_team_metric=1.0, contributions=_contribs())
    assert rk.safest_to_remove == 4    # en az katkı = en güvenli çıkış
    assert rk.most_costly_to_remove == 10  # yıldız = en maliyetli


# --------------------------------------------------------------------------- #
# B — backtest
# --------------------------------------------------------------------------- #


def test_backtest_perfect_predictions():
    samples = [(0.9, True), (0.8, True), (0.1, False), (0.2, False)]
    r = backtest(samples)
    assert r.hit_rate == 1.0
    assert r.brier_score < 0.1


def test_backtest_empty():
    r = backtest([])
    assert r.n == 0
    assert r.hit_rate == 0.0


def test_backtest_well_calibrated_detection():
    # %80 diyen 10 örneğin ~8'i gerçekleşmiş → iyi kalibre
    samples = [(0.8, True)] * 8 + [(0.8, False)] * 2
    r = backtest(samples, n_bins=5)
    assert r.well_calibrated is True


def test_backtest_miscalibrated_detection():
    # %90 diyen ama hiç gerçekleşmeyen → kötü kalibre
    samples = [(0.9, False)] * 10
    r = backtest(samples, n_bins=5)
    assert r.well_calibrated is False
    assert r.brier_score > 0.5
