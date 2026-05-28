"""engine.coaching_identity tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent, Shot
from app.engine.coaching_identity import compute_coaching_identity


def _p(team: int, sx: float = 50, sy: float = 50, ex: float = 70,
       minute: float = 10.0, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=50,
        completed=completed,
    )


def _d(team: int, x: float, action: str = "ball_recovery") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        x=x, y=50, action_type=action,  # type: ignore[arg-type]
    )


def _shot(minute: float = 11.0) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=90, y=50,
    )


def test_vector_has_8_dimensions():
    passes = [_p(11) for _ in range(100)]
    defs = [_d(11, 50) for _ in range(20)]
    r = compute_coaching_identity(11, 22, passes, defs, []).value
    v = r.vector
    # 8 boyut, hepsi 0-1 aralığında
    for field in (v.press_intensity, v.defensive_line, v.compactness,
                  v.transition_speed, v.directness, v.tempo,
                  v.attacking_third_recovery, v.channel_balance):
        assert 0.0 <= field <= 1.0


def test_high_press_archetype():
    """Yüksek PPDA tersi (yoğun pres) + yüksek tempo → high_press_possession."""
    # 500+ pas (high tempo) + çok defansif aksiyon yüksek bölgede (gegenpress)
    passes = [_p(11, sx=30, ex=50, minute=float(i % 90)) for i in range(800)]
    defs = [_d(11, 75, action="ball_recovery") for _ in range(50)]  # high zone recovery
    r = compute_coaching_identity(11, 22, passes, defs, []).value
    # Yüksek press_intensity (PPDA düşük) ve yüksek tempo
    assert r.vector.tempo >= 0.45
    assert r.archetype in ("high_press_possession", "direct_vertical")


def test_archetype_is_one_of_five():
    passes = [_p(11)]
    defs = [_d(11, 50)]
    r = compute_coaching_identity(11, 22, passes, defs, []).value
    valid = {
        "high_press_possession", "low_block_counter", "direct_vertical",
        "balanced_pragmatic", "deep_organised",
    }
    assert r.archetype in valid


def test_top_features_returns_two():
    passes = [_p(11)] * 100
    defs = [_d(11, 50)] * 20
    r = compute_coaching_identity(11, 22, passes, defs, []).value
    assert len(r.top_features) == 2


def test_audit_lists_component_engines():
    r = compute_coaching_identity(11, 22, [], [], [])
    assert "ppda" in r.audit.inputs["component_engines"]
    assert "defensive_line" in r.audit.inputs["component_engines"]
