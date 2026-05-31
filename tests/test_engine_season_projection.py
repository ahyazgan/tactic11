"""engine.season_projection — final puan projeksiyonu + puan hedefi olasılığı."""

from __future__ import annotations

import pytest

from app.engine.season_projection import (
    MatchOutcomeProb,
    compute_points_target,
    compute_season_projection,
)


def _certain_wins(n: int) -> list[MatchOutcomeProb]:
    return [MatchOutcomeProb(prob_win=1.0, prob_draw=0.0, prob_loss=0.0) for _ in range(n)]


def _coin(n: int) -> list[MatchOutcomeProb]:
    # %50 kazan / %50 kaybet → maç başına beklenen 1.5 puan
    return [MatchOutcomeProb(prob_win=0.5, prob_draw=0.0, prob_loss=0.5) for _ in range(n)]


def test_no_remaining_matches_is_point_mass():
    r = compute_season_projection(
        611, current_points=40, matches_played=20, remaining=[],
    ).value
    assert r.expected_final_points == 40
    assert r.points_p10 == r.points_p50 == r.points_p90 == 40
    assert r.max_possible_points == 40


def test_all_certain_wins_reaches_max():
    r = compute_season_projection(
        611, current_points=30, matches_played=24, remaining=_certain_wins(5),
    ).value
    assert r.expected_final_points == pytest.approx(45.0)  # 30 + 5*3
    assert r.max_possible_points == 45
    assert r.points_p50 == 45


def test_expected_points_per_match():
    r = compute_season_projection(
        611, current_points=10, matches_played=10, remaining=_coin(10),
    ).value
    # 10 maç × 1.5 beklenen puan = 15 → 25
    assert r.expected_final_points == pytest.approx(25.0)
    assert r.min_possible_points == 10
    assert r.max_possible_points == 40


def test_distribution_percentiles_ordered():
    r = compute_season_projection(
        611, current_points=10, matches_played=10, remaining=_coin(10),
    ).value
    assert r.points_p10 <= r.points_p50 <= r.points_p90


def test_low_confidence_when_few_remaining():
    r = compute_season_projection(
        611, current_points=10, matches_played=30, remaining=_coin(2),
    ).value
    assert r.low_confidence is True


def test_negative_points_raises():
    with pytest.raises(ValueError, match="negatif"):
        compute_season_projection(611, current_points=-1, matches_played=0, remaining=[])


def test_points_target_certain_when_already_reached():
    r = compute_points_target(
        611, current_points=50, matches_played=30, remaining=_coin(4),
        target_points=45,
    ).value
    assert r.prob_reach_target == pytest.approx(1.0)
    assert r.points_needed == 0
    assert r.achievable is True


def test_points_target_unreachable():
    r = compute_points_target(
        611, current_points=10, matches_played=30, remaining=_certain_wins(2),
        target_points=100,
    ).value
    assert r.achievable is False
    assert r.prob_reach_target == pytest.approx(0.0)
    assert r.wins_needed_if_only_wins == 30  # ceil(90/3)


def test_points_target_probability_between_zero_and_one():
    r = compute_points_target(
        611, current_points=20, matches_played=20, remaining=_coin(10),
        target_points=35,
    ).value
    assert 0.0 < r.prob_reach_target < 1.0


def test_audit_and_confidence_present():
    r = compute_season_projection(
        611, current_points=20, matches_played=20, remaining=_coin(6),
    )
    assert r.audit.engine == "engine.season_projection"
    assert r.confidence is not None
