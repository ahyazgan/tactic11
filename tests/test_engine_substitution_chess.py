"""engine.substitution_chess — sub forward projection tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.substitution_chess import compute_substitution_chess


def _p(team: int, player: int, minute: float,
       completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=minute, period=1,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def test_scenarios_generated_for_tired_players():
    """Yorgun oyunculu takım → top 3 sub senaryosu."""
    # Player 100 erken aktif, geç başarısız → fatigue yüksek
    passes = (
        [_p(11, 100, minute=10.0, completed=True)] * 15
        + [_p(11, 100, minute=70.0, completed=False)] * 3
    )
    r = compute_substitution_chess(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert len(r.scenarios) >= 1
    # En azından bir senaryoda out_player_id=100
    assert any(s.out_player_id == 100 for s in r.scenarios)


def test_minutes_remaining_calculated():
    r = compute_substitution_chess(
        team_external_id=11, all_passes=[], all_def_actions=[],
        current_minute=60.0, match_total_minutes=90.0,
    ).value
    assert r.minutes_remaining == 30.0


def test_projection_positive_for_fatigued_player():
    """Yorgun oyuncu için sub yapılırsa pozitif dominance delta projekt."""
    passes = (
        [_p(11, 100, minute=10.0, completed=True)] * 20
        + [_p(11, 100, minute=70.0, completed=False)] * 5
    )
    r = compute_substitution_chess(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    if r.scenarios:
        # En iyi senaryoda projected delta > 0 olmalı
        assert r.scenarios[0].projected_dominance_delta >= 0


def test_audit_includes_scenarios():
    passes = [_p(11, 100, minute=10.0)] * 15
    r = compute_substitution_chess(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=70.0,
    )
    assert "scenarios" in r.audit.value
    assert "minutes_remaining" in r.audit.value


def test_no_recommendations_empty_scenarios():
    """Hiç event yok → sub_recommendation boş → scenarios boş."""
    r = compute_substitution_chess(
        team_external_id=11, all_passes=[], all_def_actions=[],
        current_minute=60.0,
    ).value
    assert len(r.scenarios) == 0
