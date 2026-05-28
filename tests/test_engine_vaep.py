"""engine.vaep — Possession Value (KU Leuven, heuristic baseline) tests."""

from __future__ import annotations

import pytest

from app.domain import Carry, PassEvent, Shot
from app.engine.vaep import compute_vaep


def _p(team: int, player: int, sx: float, ex: float, ey: float = 50,
       completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
        completed=completed,
    )


def _c(team: int, player: int, sx: float, ex: float) -> Carry:
    return Carry(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=50,
    )


def _shot(player: int, x: float, y: float = 50, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=player,
        minute=10.0, x=x, y=y, is_goal=is_goal,
    )


def test_forward_pass_positive_vaep():
    """Savunmadan hücuma uzun ileri pas → pozitif VAEP."""
    passes = [_p(11, 100, sx=20, ex=80)]
    r = compute_vaep(
        team_external_id=11, all_passes=passes, all_carries=[], all_shots=[],
    ).value
    assert r.vaep_value > 0
    assert r.by_action["passes"] > 0


def test_backward_pass_negative_or_zero():
    """Geri pas → negatif veya 0 ΔxT."""
    passes = [_p(11, 100, sx=80, ex=20)]
    r = compute_vaep(
        team_external_id=11, all_passes=passes, all_carries=[], all_shots=[],
    ).value
    assert r.vaep_value <= 0


def test_incomplete_pass_concede_penalty():
    """Tamamlanmamış pas concede değeri ekler."""
    passes = [_p(11, 100, sx=20, ex=80, completed=False)]
    r = compute_vaep(
        team_external_id=11, all_passes=passes, all_carries=[], all_shots=[],
    ).value
    assert r.sum_concede_value > 0


def test_player_filter():
    """Sadece bir oyuncu için."""
    passes = [
        _p(11, 100, sx=20, ex=80),
        _p(11, 200, sx=20, ex=80),  # farklı oyuncu
    ]
    r = compute_vaep(
        player_external_id=100, all_passes=passes,
        all_carries=[], all_shots=[],
    ).value
    assert r.total_actions == 1


def test_shot_close_to_goal_high_value():
    """Yakın şut yüksek VAEP score."""
    shots = [_shot(100, x=98, y=50)]
    r = compute_vaep(
        team_external_id=11, all_passes=[], all_carries=[], all_shots=shots,
    ).value
    assert r.sum_score_value >= 0.5


def test_carry_into_attack():
    """Carry ileriye → pozitif VAEP."""
    carries = [_c(11, 100, sx=30, ex=70)]
    r = compute_vaep(
        team_external_id=11, all_passes=[], all_carries=carries, all_shots=[],
    ).value
    assert r.by_action["carries"] > 0


def test_per_90_normalization():
    passes = [_p(11, 100, sx=20, ex=80) for _ in range(2)]
    r = compute_vaep(
        player_external_id=100, all_passes=passes, all_carries=[], all_shots=[],
        minutes_played=45.0,
    ).value
    assert r.vaep_per_90 is not None
    # 2 forward pasın vaep'i × (90/45) = 2x
    assert r.vaep_per_90 == round(r.vaep_value * 2, 3)


def test_no_subject_raises():
    with pytest.raises(ValueError, match="verilmeli"):
        compute_vaep(all_passes=[], all_carries=[], all_shots=[])


def test_model_version_is_baseline():
    """v1 baseline — sklearn-free heuristic."""
    r = compute_vaep(team_external_id=11, all_passes=[],
                     all_carries=[], all_shots=[])
    assert r.value.model_version == "1-baseline"
    assert "heuristic_baseline_xt_grid" in r.audit.inputs["model_type"]


def test_audit_breakdown():
    passes = [_p(11, 100, sx=20, ex=80)]
    r = compute_vaep(
        team_external_id=11, all_passes=passes, all_carries=[], all_shots=[],
    )
    assert r.audit.engine == "engine.vaep"
    assert "vaep_value" in r.audit.value
