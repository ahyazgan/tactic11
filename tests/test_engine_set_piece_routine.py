"""engine.set_piece_routine — routine builder tests."""

from __future__ import annotations

from app.domain import Shot
from app.engine.set_piece_routine import compute_set_piece_routine


def _shot(x: float, y: float, pattern: str = "corner_kick",
          is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=1,
        minute=10.0, x=x, y=y, pattern=pattern,  # type: ignore[arg-type]
        is_goal=is_goal,
    )


def test_routine_recommends_zone_where_opp_weak_and_we_strong():
    """Rakip near_post'ta zayıf + biz near_post'ta güçlü → top recommendation."""
    # Bizim ofansif: near_post'ta 2/2 (100%)
    my_shots = [_shot(92, 20, is_goal=True), _shot(92, 20, is_goal=True)]
    # Rakip defansif: near_post yedi 1/2 (50%)
    opp_def = [_shot(92, 20, is_goal=True), _shot(92, 20, is_goal=False)]
    # Rakip ofansif (avoid için)
    opp_off = [_shot(96, 50, is_goal=True)]
    r = compute_set_piece_routine(
        my_team_external_id=11, opponent_team_external_id=22,
        my_offensive_shots=my_shots, opponent_defensive_shots=opp_def,
        opponent_offensive_shots=opp_off,
        matches_analyzed=5,
    ).value
    # near_post öne çıkmalı
    assert any(r.target_zone == "near_post" for r in r.top_recommendations)


def test_avoid_zone_set_from_opp_offensive():
    """Rakip central_6yd'ya yığınak yapıyorsa, avoid_zone=central_6yd."""
    my_shots = [_shot(92, 20, is_goal=True)]
    opp_def = [_shot(92, 20, is_goal=True)]
    opp_off = [_shot(96, 50, is_goal=True), _shot(96, 50, is_goal=True)]
    r = compute_set_piece_routine(
        my_team_external_id=11, opponent_team_external_id=22,
        my_offensive_shots=my_shots, opponent_defensive_shots=opp_def,
        opponent_offensive_shots=opp_off,
    ).value
    assert r.avoid_zone == "central_6yd"


def test_technique_mapped_for_each_zone():
    """Her zone önerisi technique içerir."""
    my_shots = [_shot(92, 20, is_goal=True)]
    opp_def = [_shot(92, 20, is_goal=True)]
    opp_off = [_shot(92, 20, is_goal=True)]
    r = compute_set_piece_routine(
        my_team_external_id=11, opponent_team_external_id=22,
        my_offensive_shots=my_shots, opponent_defensive_shots=opp_def,
        opponent_offensive_shots=opp_off,
    ).value
    for rec in r.top_recommendations:
        assert rec.technique  # non-empty
        assert rec.rationale  # Türkçe


def test_set_piece_type_filter_corner_kick():
    """set_piece_type=corner_kick → sadece corner'lar."""
    my_shots = [
        _shot(92, 20, pattern="corner_kick", is_goal=True),
        _shot(92, 20, pattern="free_kick", is_goal=True),
    ]
    opp_def = my_shots
    opp_off = my_shots
    r = compute_set_piece_routine(
        my_team_external_id=11, opponent_team_external_id=22,
        my_offensive_shots=my_shots, opponent_defensive_shots=opp_def,
        opponent_offensive_shots=opp_off,
        set_piece_type="corner_kick",
    ).value
    assert r.set_piece_type == "corner_kick"


def test_audit_includes_recommendations():
    my_shots = [_shot(92, 20, is_goal=True)]
    opp_def = [_shot(92, 20, is_goal=True)]
    opp_off = [_shot(96, 50, is_goal=True)]
    r = compute_set_piece_routine(
        my_team_external_id=11, opponent_team_external_id=22,
        my_offensive_shots=my_shots, opponent_defensive_shots=opp_def,
        opponent_offensive_shots=opp_off,
    )
    assert "top_recommendations" in r.audit.value
    assert "avoid_zone" in r.audit.value
