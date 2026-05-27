"""engine.formation_matcher tests."""

from __future__ import annotations

from app.engine.formation_matcher import (
    FormationMatchupRecord,
    best_formations_against,
    compute_formation_matchup,
)


def _record(mid: int, my: str, opp: str, my_g: int, opp_g: int) -> FormationMatchupRecord:
    return FormationMatchupRecord(
        match_external_id=mid, my_formation=my, opp_formation=opp,
        my_goals=my_g, opp_goals=opp_g,
    )


def test_no_matching_records_returns_zero_report():
    r = compute_formation_matchup("4-3-3", "4-2-3-1", [
        _record(1, "3-5-2", "4-4-2", 2, 1),
    ])
    v = r.value
    assert v.matches_played == 0
    assert v.win_rate == 0.0
    assert v.avg_goal_diff == 0.0


def test_aggregates_win_draw_loss():
    records = [
        _record(1, "4-3-3", "4-2-3-1", 3, 1),  # win
        _record(2, "4-3-3", "4-2-3-1", 1, 1),  # draw
        _record(3, "4-3-3", "4-2-3-1", 0, 2),  # loss
        _record(4, "4-3-3", "4-2-3-1", 2, 0),  # win
        _record(5, "3-5-2", "4-2-3-1", 4, 0),  # farklı my_formation, sayılmaz
    ]
    r = compute_formation_matchup("4-3-3", "4-2-3-1", records)
    v = r.value
    assert v.matches_played == 4
    assert v.wins == 2
    assert v.draws == 1
    assert v.losses == 1
    assert v.win_rate == 0.5
    # Goal diff: (3-1) + (1-1) + (0-2) + (2-0) = 2+0-2+2 = 2 → /4 = 0.5
    assert v.avg_goal_diff == 0.5
    assert v.avg_my_goals == 1.5  # 6/4
    assert v.avg_opp_goals == 1.0


def test_outcome_property():
    assert _record(1, "a", "b", 2, 1).outcome == "win"
    assert _record(1, "a", "b", 1, 1).outcome == "draw"
    assert _record(1, "a", "b", 0, 2).outcome == "loss"


def test_audit_records_formula_and_inputs():
    r = compute_formation_matchup("4-3-3", "4-2-3-1", [
        _record(1, "4-3-3", "4-2-3-1", 2, 1),
    ])
    assert r.audit.engine == "engine.formation_matcher"
    assert r.audit.inputs["my_formation"] == "4-3-3"
    assert r.audit.inputs["records_considered"] == 1
    assert "win_rate" in str(r.audit.value)


# --------------------------------------------------------------------------- #
# best_formations_against — sıralama + min_matches filter
# --------------------------------------------------------------------------- #


def test_best_formations_against_orders_by_win_rate():
    """3-5-2 → 4-2-3-1'e karşı %100 win (3 maç); 4-3-3 → %66 win (3 maç)."""
    records = [
        # 3-5-2 vs 4-2-3-1 — 3 win
        _record(1, "3-5-2", "4-2-3-1", 2, 0),
        _record(2, "3-5-2", "4-2-3-1", 3, 1),
        _record(3, "3-5-2", "4-2-3-1", 1, 0),
        # 4-3-3 vs 4-2-3-1 — 2 win 1 loss
        _record(4, "4-3-3", "4-2-3-1", 2, 1),
        _record(5, "4-3-3", "4-2-3-1", 1, 0),
        _record(6, "4-3-3", "4-2-3-1", 0, 2),
    ]
    top = best_formations_against("4-2-3-1", records, min_matches=3, top_n=5)
    assert len(top) == 2
    assert top[0].my_formation == "3-5-2"
    assert top[0].win_rate == 1.0
    assert top[1].my_formation == "4-3-3"
    assert top[1].win_rate < 1.0


def test_best_formations_filters_small_samples():
    """min_matches altında olan formation çiftleri atlanmalı."""
    records = [
        _record(1, "4-3-3", "4-2-3-1", 5, 0),  # 1 maç (min_matches=3 filtreler)
        _record(2, "3-5-2", "4-2-3-1", 1, 0),
        _record(3, "3-5-2", "4-2-3-1", 2, 1),
        _record(4, "3-5-2", "4-2-3-1", 0, 0),
    ]
    top = best_formations_against("4-2-3-1", records, min_matches=3)
    assert len(top) == 1
    assert top[0].my_formation == "3-5-2"


def test_best_formations_top_n_limits():
    """Birçok formation çifti varsa top_n kadarını döndür."""
    formations = ["4-3-3", "3-5-2", "4-4-2", "4-2-3-1", "5-3-2"]
    records = []
    mid = 1
    for f in formations:
        for _ in range(3):
            records.append(_record(mid, f, "4-2-3-1", 1, 0))
            mid += 1
    top = best_formations_against("4-2-3-1", records, min_matches=3, top_n=2)
    assert len(top) == 2
