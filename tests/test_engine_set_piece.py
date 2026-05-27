"""engine.set_piece tests."""

from __future__ import annotations

import pytest

from app.domain import Shot
from app.engine.set_piece import (
    SET_PIECE_PATTERNS,
    compute_set_piece_efficiency,
)


def _shot(**kw) -> Shot:
    base = dict(
        sport="football", match_external_id=1, player_external_id=10,
        minute=20.0, x=85.0, y=50.0, body_part="right_foot",
        pattern="open_play", is_goal=False,
    )
    base.update(kw)
    return Shot(**base)  # type: ignore[arg-type]


def test_set_piece_patterns_set():
    assert "corner_kick" in SET_PIECE_PATTERNS
    assert "free_kick" in SET_PIECE_PATTERNS
    assert "set_piece" in SET_PIECE_PATTERNS
    assert "open_play" not in SET_PIECE_PATTERNS
    assert "penalty" not in SET_PIECE_PATTERNS


def test_open_play_shots_excluded():
    """open_play şutlar set-piece sayılmaz."""
    shots = [
        _shot(pattern="open_play", is_goal=True),
        _shot(pattern="open_play", is_goal=False),
    ]
    r = compute_set_piece_efficiency(611, shots, role="offensive")
    assert r.value.shot_count == 0
    assert r.value.goal_count == 0


def test_corner_kick_only_filter():
    """set_piece_type='corner_kick' → sadece köşe şutları."""
    shots = [
        _shot(pattern="corner_kick", is_goal=True),
        _shot(pattern="corner_kick", is_goal=False),
        _shot(pattern="free_kick", is_goal=True),
    ]
    r = compute_set_piece_efficiency(611, shots, set_piece_type="corner_kick")
    assert r.value.shot_count == 2
    assert r.value.goal_count == 1
    assert r.value.conversion_rate == 0.5


def test_all_set_pieces_aggregate():
    """set_piece_type='all' → corner + free_kick + set_piece toplamı."""
    shots = [
        _shot(pattern="corner_kick", is_goal=False),
        _shot(pattern="free_kick", is_goal=True),
        _shot(pattern="set_piece", is_goal=False),
        _shot(pattern="open_play", is_goal=True),  # hariç
    ]
    r = compute_set_piece_efficiency(611, shots, set_piece_type="all")
    assert r.value.shot_count == 3
    assert r.value.goal_count == 1
    assert r.value.conversion_rate == pytest.approx(1 / 3, abs=1e-3)


def test_offensive_role_default():
    r = compute_set_piece_efficiency(611, [_shot(pattern="corner_kick")])
    assert r.value.role == "offensive"


def test_invalid_role_raises():
    with pytest.raises(ValueError, match="role"):
        compute_set_piece_efficiency(611, [], role="midfield")  # type: ignore[arg-type]


def test_xg_calculation_when_use_xg_true():
    """use_xg=True → engine.xg.compute_shot_xg(geometric) ile total_xg dolu."""
    shots = [
        _shot(pattern="corner_kick", x=88, y=50),
        _shot(pattern="free_kick", x=80, y=45),
    ]
    r = compute_set_piece_efficiency(611, shots, use_xg=True)
    assert r.value.total_xg is not None
    assert r.value.total_xg > 0
    assert r.value.xg_per_shot is not None


def test_xg_not_calculated_when_use_xg_false():
    """Default use_xg=False → total_xg None."""
    r = compute_set_piece_efficiency(
        611, [_shot(pattern="corner_kick")], use_xg=False,
    )
    assert r.value.total_xg is None


def test_empty_input_returns_zero_report():
    r = compute_set_piece_efficiency(611, [])
    assert r.value.shot_count == 0
    assert r.value.goal_count == 0
    assert r.value.conversion_rate == 0.0


def test_audit_records_formula():
    r = compute_set_piece_efficiency(611, [_shot(pattern="corner_kick")])
    assert r.audit.engine == "engine.set_piece"
    assert "conversion_rate" in r.audit.formula


def test_defensive_role_tracks_opponent_shots():
    """role='defensive' farklı role mark eder; aynı veri agregasyonu."""
    r = compute_set_piece_efficiency(
        611, [_shot(pattern="corner_kick", is_goal=True)], role="defensive",
    )
    assert r.value.role == "defensive"
    assert r.value.shot_count == 1
    assert r.value.goal_count == 1
