"""engine.transfer — değerleme, yedek bulma, kontrat riski, recruitment fit."""

from __future__ import annotations

import pytest

from app.engine.transfer import (
    compute_contract_risk,
    compute_recruitment_fit,
    compute_replacement_options,
    compute_transfer_value,
)


# --------------------------------------------------------------------------- #
# transfer_value_estimator
# --------------------------------------------------------------------------- #


def test_value_higher_for_better_rating():
    low = compute_transfer_value(1, rating_avg=6.3, minutes_played=2000, matches_played=25, age=25).value
    high = compute_transfer_value(2, rating_avg=7.6, minutes_played=2000, matches_played=25, age=25).value
    assert high.value_score > low.value_score


def test_value_peak_age_beats_old():
    peak = compute_transfer_value(1, rating_avg=7.2, minutes_played=2000, matches_played=25, age=25).value
    old = compute_transfer_value(2, rating_avg=7.2, minutes_played=2000, matches_played=25, age=34).value
    assert peak.value_score > old.value_score
    assert peak.age_factor == pytest.approx(1.0)


def test_value_tier_labels():
    elite = compute_transfer_value(1, rating_avg=8.0, minutes_played=2700, matches_played=30, age=25).value
    fringe = compute_transfer_value(2, rating_avg=6.0, minutes_played=200, matches_played=3, age=33).value
    assert elite.tier == "elite"
    assert fringe.tier in ("fringe", "squad")
    assert fringe.low_confidence is True


def test_value_score_in_range():
    v = compute_transfer_value(1, rating_avg=7.0, minutes_played=1500, matches_played=20, age=27).value
    assert 0.0 <= v.value_score <= 100.0
    assert "proxy" in v.note.lower()


# --------------------------------------------------------------------------- #
# replacement_finder
# --------------------------------------------------------------------------- #


def test_replacement_ranks_by_fit():
    cands = [
        {"player_external_id": 10, "similarity": 0.9, "minutes_played": 2400, "age": 25},
        {"player_external_id": 11, "similarity": 0.5, "minutes_played": 800, "age": 31},
        {"player_external_id": 12, "similarity": 0.85, "minutes_played": 2200, "age": 23},
    ]
    rep = compute_replacement_options(99, cands, top_n=3).value
    assert rep.top_candidates[0].player_external_id in (10, 12)  # yüksek sim + müsait
    scores = [c.fit_score for c in rep.top_candidates]
    assert scores == sorted(scores, reverse=True)


def test_replacement_filters_low_similarity():
    cands = [
        {"player_external_id": 10, "similarity": 0.1, "minutes_played": 2400, "age": 25},
        {"player_external_id": 11, "similarity": 0.6, "minutes_played": 2000, "age": 24},
    ]
    rep = compute_replacement_options(99, cands, min_similarity=0.3).value
    ids = {c.player_external_id for c in rep.top_candidates}
    assert ids == {11}  # 10 elendi (sim<0.3)


def test_replacement_flags():
    cands = [{"player_external_id": 10, "similarity": 0.8, "minutes_played": 2500, "age": 19}]
    rep = compute_replacement_options(99, cands).value
    c = rep.top_candidates[0]
    assert "young_prospect" in c.flags
    assert "high_availability" in c.flags


# --------------------------------------------------------------------------- #
# contract_risk
# --------------------------------------------------------------------------- #


def test_contract_risk_high_for_valuable_short_contract():
    r = compute_contract_risk(1, days_remaining=120, value_score=85, age=25).value
    assert r.risk_level in ("critical", "high")
    assert r.recommendation == "renew_now"


def test_contract_risk_low_for_long_contract():
    r = compute_contract_risk(1, days_remaining=900, value_score=70, age=25).value
    assert r.risk_level in ("low", "medium")


def test_contract_risk_sell_aging():
    r = compute_contract_risk(1, days_remaining=200, value_score=65, age=33).value
    assert r.recommendation == "sell_to_recoup"


def test_contract_risk_let_expire_low_value():
    r = compute_contract_risk(1, days_remaining=200, value_score=15, age=27).value
    assert r.recommendation == "let_expire"


# --------------------------------------------------------------------------- #
# recruitment_fit
# --------------------------------------------------------------------------- #


def test_recruitment_strong_fit_same_position_similar_style():
    r = compute_recruitment_fit(
        1, candidate_position="M", needed_position="M",
        candidate_metrics={"pass_pct": 0.85, "shots_p90": 1.2},
        target_metrics={"pass_pct": 0.86, "shots_p90": 1.1},
        value_score=75,
    ).value
    assert r.position_match is True
    assert r.verdict == "strong_fit"


def test_recruitment_weak_fit_wrong_position():
    r = compute_recruitment_fit(
        1, candidate_position="G", needed_position="F",
        candidate_metrics={"shots_p90": 0.0},
        target_metrics={"shots_p90": 3.0},
        value_score=40,
    ).value
    assert r.position_match is False
    assert r.verdict in ("weak_fit", "possible_fit")


def test_recruitment_no_common_metrics_neutral_style():
    r = compute_recruitment_fit(
        1, candidate_position="D", needed_position="D",
        candidate_metrics={"a": 1.0}, target_metrics={"b": 2.0},
        value_score=50,
    ).value
    assert r.style_alignment == pytest.approx(0.5)


def test_transfer_engines_have_audit():
    for r in (
        compute_transfer_value(1, rating_avg=7.0, minutes_played=1500, matches_played=20, age=25),
        compute_replacement_options(1, [{"player_external_id": 2, "similarity": 0.5, "minutes_played": 900}]),
        compute_contract_risk(1, days_remaining=300, value_score=60),
        compute_recruitment_fit(1, candidate_position="M", needed_position="M",
                                candidate_metrics={"x": 1.0}, target_metrics={"x": 1.0}),
    ):
        assert r.audit.engine.startswith("engine.")
        assert r.confidence is not None
