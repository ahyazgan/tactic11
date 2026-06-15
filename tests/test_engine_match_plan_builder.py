"""Match Plan Builder testleri (kompozit)."""
from __future__ import annotations

from app.engine.match_plan_builder import MatchPlanContext, compute_match_plan
from app.engine.threat_pathway import PathwayEvent


def test_basic_plan_has_headline_and_lines():
    ctx = MatchPlanContext(
        our_formation="4-3-3",
        opp_formation="4-2-3-1",
        opponent_style="atletico_compact",
        set_piece_type="corner",
        set_piece_side="long",
        our_attributes={"aerial": 0.8, "set_piece": 0.7},
    )
    r = compute_match_plan(ctx).value
    assert r.our_formation == "4-3-3"
    assert r.opp_formation == "4-2-3-1"
    assert r.headline
    assert "4-3-3 vs 4-2-3-1" in r.headline
    assert len(r.plan_lines) >= 2
    assert any("Formasyon" in line for line in r.plan_lines)
    assert any("Set-piece" in line for line in r.plan_lines)


def test_matchup_vector_has_8_dimensions():
    ctx = MatchPlanContext(our_formation="4-3-3", opp_formation="4-2-3-1")
    r = compute_match_plan(ctx).value
    # 8 vektör boyut
    expected = {
        "our_xt_expected", "opp_xt_expected", "our_ppda_advantage",
        "midfield_control", "width_clash", "set_piece_clash",
        "transition_speed", "space_behind_lines",
    }
    assert expected.issubset(set(r.matchup_vector.keys()))


def test_set_piece_top_filled_when_attributes_strong():
    ctx = MatchPlanContext(
        our_formation="4-3-3", opp_formation="4-4-2",
        set_piece_type="corner", set_piece_side="long",
        our_attributes={"aerial": 0.9, "jumping_reach": 0.8},
    )
    r = compute_match_plan(ctx).value
    assert len(r.set_piece_top) >= 1
    assert "name" in r.set_piece_top[0]
    assert "label" in r.set_piece_top[0]
    assert "score" in r.set_piece_top[0]


def test_threat_lane_when_events_provided():
    events = [
        PathwayEvent(start_y=40, end_y=10, threat_weight=0.3, is_shot=True),
        PathwayEvent(start_y=40, end_y=15, threat_weight=0.4),
    ]
    ctx = MatchPlanContext(
        our_formation="4-3-3", opp_formation="4-2-3-1",
        recent_threat_events=events,
    )
    r = compute_match_plan(ctx).value
    assert r.threat_top_lane == "left_wing"
    assert r.threat_advice is not None
    assert any("Lane planı" in line for line in r.plan_lines)


def test_threat_skipped_when_no_events():
    ctx = MatchPlanContext(our_formation="4-3-3", opp_formation="4-2-3-1")
    r = compute_match_plan(ctx).value
    assert r.threat_top_lane is None
    assert r.threat_advice is None


def test_audit_has_sub_audits():
    ctx = MatchPlanContext(
        our_formation="4-3-3", opp_formation="4-2-3-1",
        our_attributes={"aerial": 0.7},
    )
    res = compute_match_plan(ctx)
    a = res.audit
    assert "sub_audits" in a.inputs
    assert "formation_matchup" in a.inputs["sub_audits"]
    assert "set_piece_library" in a.inputs["sub_audits"]
    assert a.value["our_formation"] == "4-3-3"
    assert "matchup_vector" in a.value


def test_atletico_bonus_set_piece_score_higher():
    """opponent_style=atletico_compact → set-piece score +10 bonus."""
    ctx_base = MatchPlanContext(
        our_formation="4-3-3", opp_formation="4-4-2",
        set_piece_type="corner", set_piece_side="long",
        our_attributes={"aerial": 0.7},
    )
    ctx_atl = MatchPlanContext(
        our_formation="4-3-3", opp_formation="4-4-2",
        opponent_style="atletico_compact",
        set_piece_type="corner", set_piece_side="long",
        our_attributes={"aerial": 0.7},
    )
    r_base = compute_match_plan(ctx_base).value
    r_atl = compute_match_plan(ctx_atl).value
    if r_base.set_piece_top and r_atl.set_piece_top:
        assert r_atl.set_piece_top[0]["score"] - r_base.set_piece_top[0]["score"] >= 9.5


def test_plan_lines_fallback_when_minimal_input():
    """Çok az girdi → plan satırları yine de oluşur."""
    ctx = MatchPlanContext(our_formation="4-3-3", opp_formation="4-3-3")
    r = compute_match_plan(ctx).value
    assert len(r.plan_lines) >= 1


def test_unknown_formation_pair_yields_notes():
    ctx = MatchPlanContext(our_formation="9-0-1", opp_formation="0-9-1")
    r = compute_match_plan(ctx).value
    assert r.notes or r.matchup_vector  # ya not ya nötr fallback


def test_headline_includes_ppda_advantage_value():
    ctx = MatchPlanContext(our_formation="4-3-3", opp_formation="5-4-1")
    r = compute_match_plan(ctx).value
    assert "PPDA" in r.headline
    assert "kontrol" in r.headline.lower() or "orta saha" in r.headline.lower()
