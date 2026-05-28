"""engine.match_dominance tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.match_dominance import compute_match_dominance


def _p(team: int, ex: float = 70) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=50, start_y=50, end_x=ex, end_y=50,
    )


def _shot(x: float = 95, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=10.0, x=x, y=50, is_goal=is_goal,
    )


def test_dominant_team_high_score():
    """Bizim 8 yakın şut + 80% possession + final third pasları → dominant."""
    team_shots = [_shot() for _ in range(8)]
    opp_shots = [_shot() for _ in range(1)]
    # 16 bizim pas (hepsi son üçe), 4 rakip pas (kendi yarısında)
    passes = (
        [_p(11, ex=80) for _ in range(16)] +
        [_p(22, ex=30) for _ in range(4)]
    )
    r = compute_match_dominance(
        team_external_id=11, opponent_team_external_id=22,
        team_shots=team_shots, opponent_shots=opp_shots,
        all_passes=passes,
    ).value
    assert r.dominance_score > 0
    assert r.label == "dominant"


def test_dominated_negative_score():
    team_shots = [_shot() for _ in range(1)]
    opp_shots = [_shot() for _ in range(8)]
    passes = (
        [_p(11, ex=30) for _ in range(4)] +
        [_p(22, ex=80) for _ in range(16)]
    )
    r = compute_match_dominance(
        team_external_id=11, opponent_team_external_id=22,
        team_shots=team_shots, opponent_shots=opp_shots,
        all_passes=passes,
    ).value
    assert r.dominance_score < 0
    assert r.label == "dominated"


def test_balanced_match():
    team_shots = [_shot() for _ in range(3)]
    opp_shots = [_shot() for _ in range(3)]
    passes = [_p(11) for _ in range(10)] + [_p(22) for _ in range(10)]
    r = compute_match_dominance(
        team_external_id=11, opponent_team_external_id=22,
        team_shots=team_shots, opponent_shots=opp_shots,
        all_passes=passes,
    ).value
    assert r.label == "balanced"
    assert abs(r.dominance_score) < 2.0


def test_score_clipped_to_range():
    """Extreme veriyle bile score [-10, 10] arasında kalmalı."""
    team_shots = [_shot() for _ in range(50)]
    opp_shots = []
    passes = [_p(11, ex=85) for _ in range(100)]
    r = compute_match_dominance(
        team_external_id=11, opponent_team_external_id=22,
        team_shots=team_shots, opponent_shots=opp_shots,
        all_passes=passes,
    ).value
    assert -10.0 <= r.dominance_score <= 10.0
