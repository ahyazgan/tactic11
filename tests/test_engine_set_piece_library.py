"""Set-Piece Pattern Library testleri."""
from __future__ import annotations

from app.engine.set_piece_library import (
    SetPieceContext,
    compute_set_piece_recommendation,
    list_patterns,
)


def test_kb_has_min_15_patterns():
    patterns = list_patterns()
    assert len(patterns) >= 15
    types = {p.type for p in patterns}
    assert {"corner", "free_kick", "throw_in", "penalty"}.issubset(types)


def test_corner_long_aerial_team_top_pick():
    """Hava topu üstün takım, long corner → inswinger/outswinger top picks."""
    ctx = SetPieceContext(
        type="corner", side="long",
        our_attributes={"aerial": 0.85, "jumping_reach": 0.8,
                        "anticipation": 0.7, "timing": 0.7},
    )
    r = compute_set_piece_recommendation(ctx, top_n=3).value
    names = [p.name for p in r.top_recommendations]
    assert "corner_inswinger_near_post" in names or \
        "corner_outswinger_far_post" in names


def test_corner_short_picks_short_patterns():
    ctx = SetPieceContext(
        type="corner", side="short",
        our_attributes={"technique": 0.8, "vision": 0.7,
                        "close_control": 0.75, "dribble": 0.7,
                        "cross_quality": 0.7},
    )
    r = compute_set_piece_recommendation(ctx, top_n=3).value
    names = [p.name for p in r.top_recommendations]
    assert any("corner_short" in n for n in names)


def test_free_kick_direct_shot_strong_shooter():
    ctx = SetPieceContext(
        type="free_kick",
        our_attributes={"shot_power": 0.9, "technique": 0.85,
                        "set_piece": 0.8},
    )
    r = compute_set_piece_recommendation(ctx, top_n=2).value
    names = [p.name for p in r.top_recommendations]
    assert "free_kick_direct_shot" in names or \
        "free_kick_wall_around" in names


def test_penalty_panenka_for_cool_taker():
    ctx = SetPieceContext(
        type="penalty",
        our_attributes={"composure": 0.95, "technique": 0.85,
                        "mind_game": 0.9},
    )
    r = compute_set_piece_recommendation(ctx, top_n=2).value
    names = [p.name for p in r.top_recommendations]
    assert "penalty_panenka" in names or "penalty_low_corner" in names


def test_style_bonus_atletico_set_piece():
    """Rakip Atletico-kompakt → set-piece bonus +10 → daha yüksek score."""
    ctx_no = SetPieceContext(
        type="corner", side="long",
        our_attributes={"aerial": 0.7},
    )
    ctx_atletico = SetPieceContext(
        type="corner", side="long",
        our_attributes={"aerial": 0.7},
        opponent_style="atletico_compact",
    )
    r_no = compute_set_piece_recommendation(ctx_no, top_n=1).value
    r_atletico = compute_set_piece_recommendation(ctx_atletico, top_n=1).value
    assert r_atletico.top_recommendations[0].score - \
        r_no.top_recommendations[0].score >= 9.5


def test_throw_in_long_target():
    ctx = SetPieceContext(
        type="throw_in",
        our_attributes={"long_throw": 0.9, "aerial": 0.8, "hold_up": 0.75},
    )
    r = compute_set_piece_recommendation(ctx).value
    names = [p.name for p in r.top_recommendations]
    assert "throw_long_target_man" in names or \
        "throw_short_combination" in names


def test_unknown_type_returns_empty():
    ctx = SetPieceContext(type="bicycle_kick")
    r = compute_set_piece_recommendation(ctx).value
    assert len(r.top_recommendations) == 0
    assert any("bulunamadı" in n for n in r.notes)


def test_audit_complete():
    ctx = SetPieceContext(
        type="corner", side="long",
        our_attributes={"aerial": 0.8},
    )
    res = compute_set_piece_recommendation(ctx)
    a = res.audit.value
    assert "type" in a
    assert "candidates" in a
    assert "top_names" in a
    assert "summary" in a


def test_list_patterns_returns_all():
    patterns = list_patterns()
    types = [p.type for p in patterns]
    # Her ana tip için en az 1 pattern var
    for t in ("corner", "free_kick", "throw_in", "penalty"):
        assert types.count(t) >= 1
