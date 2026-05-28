"""engine.overperformance tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.overperformance import compute_overperformance


def _shot(player: int, x: float, y: float, is_goal: bool, minute: float = 10.0) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=player,
        minute=minute, x=x, y=y, is_goal=is_goal,
    )


def _pass(player: int, minute: float, key_pass: bool, assist: bool = False) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=60, start_y=50, end_x=85, end_y=50,
        key_pass=key_pass, assist=assist,
    )


def test_clinical_finisher_goals_above_xg():
    """Uzak şutlardan goller → low xG, high G → clinical overperformance."""
    # 5 uzak şut, hepsi gol (gerçek dışı ama test için)
    shots = [_shot(100, x=70, y=50, is_goal=True) for _ in range(5)]
    r = compute_overperformance(
        player_external_id=100, all_passes=[], all_shots=shots,
    ).value
    assert r.goals == 5
    assert r.xg < r.goals
    assert r.g_minus_xg > 0
    assert r.label == "clinical"


def test_underperforming_xg_above_goals():
    """Yakın şutlar ama hiç gol yok → high xG, 0 G → underperforming."""
    shots = [_shot(100, x=95, y=50, is_goal=False) for _ in range(5)]
    r = compute_overperformance(
        player_external_id=100, all_passes=[], all_shots=shots,
    ).value
    assert r.goals == 0
    assert r.xg > 0
    assert r.label == "underperforming"


def test_xa_paired_with_shot_in_window():
    """key_pass + sonraki şut → xA o şutun xG'si."""
    passes = [_pass(100, minute=10.0, key_pass=True, assist=True)]
    shots = [_shot(200, x=95, y=50, is_goal=True, minute=10.05)]
    r = compute_overperformance(
        player_external_id=100, all_passes=passes, all_shots=shots,
    ).value
    assert r.assists == 1
    assert r.xa > 0


def test_insufficient_data():
    r = compute_overperformance(
        player_external_id=100, all_passes=[], all_shots=[],
    ).value
    assert r.label == "insufficient_data"


def test_other_player_excluded():
    shots = [_shot(200, x=95, y=50, is_goal=True)]
    r = compute_overperformance(
        player_external_id=100, all_passes=[], all_shots=shots,
    ).value
    assert r.goals == 0
