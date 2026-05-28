"""engine.match_phase tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent, Shot
from app.engine.match_phase import (
    compute_match_phases,
    compute_score_state_effects,
)


def _shot(minute: float, x: float = 88, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=1, player_external_id=10,
        minute=minute, x=x, y=50.0, body_part="right_foot",
        pattern="open_play", is_goal=is_goal,
    )


def _pass(minute: float, period: int = 1, team_id: int = 1, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=1, team_external_id=team_id,
        minute=minute, period=period,
        start_x=50.0, start_y=50.0, end_x=80.0, end_y=50.0,
        completed=completed,
    )


def _def(minute: float, period: int = 1, team_id: int = 1) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=1,
        player_external_id=2, team_external_id=team_id,
        minute=minute, period=period, x=70.0, y=50.0,
        action_type="tackle",
    )


# --------------------------------------------------------------------------- #
# Match phases
# --------------------------------------------------------------------------- #


def test_phases_split_by_minute():
    """1H (1-45) + 2H (46-90) ayrı agregat."""
    home_shots = [_shot(20), _shot(30), _shot(60), _shot(80)]
    home_passes = [_pass(10, 1), _pass(60, 2)]
    home_defs = [_def(20, 1), _def(70, 2)]
    r = compute_match_phases(
        match_external_id=1, home_team_id=10, away_team_id=20,
        home_shots=home_shots, away_shots=[],
        home_passes=home_passes, away_passes=[],
        home_def_actions=home_defs, away_def_actions=[],
    )
    home_first = r.value.home_phases[0]
    home_second = r.value.home_phases[1]
    assert home_first.shots_count == 2  # min 20 + 30
    assert home_second.shots_count == 2  # min 60 + 80
    assert home_first.passes_count == 1
    assert home_second.passes_count == 1


def test_extra_time_phase_added_when_minute_above_90():
    home_shots = [_shot(105)]
    r = compute_match_phases(
        match_external_id=1, home_team_id=10, away_team_id=20,
        home_shots=home_shots, away_shots=[],
        home_passes=[], away_passes=[],
        home_def_actions=[], away_def_actions=[],
    )
    # Sadece minute > 90 olduğunda ET phase oluşur
    et_phases = [p for p in r.value.home_phases if p.phase == "extra_time"]
    assert len(et_phases) == 1
    assert et_phases[0].shots_count == 1


def test_total_xg_per_phase_non_negative():
    home_shots = [_shot(30, x=85), _shot(75, x=85)]
    r = compute_match_phases(
        match_external_id=1, home_team_id=10, away_team_id=20,
        home_shots=home_shots, away_shots=[],
        home_passes=[], away_passes=[],
        home_def_actions=[], away_def_actions=[],
    )
    for p in r.value.home_phases:
        assert p.total_xg >= 0


def test_team_separation():
    """Home + away ayrı listelerden agregat."""
    home = [_shot(20)]
    away = [_shot(70)]
    r = compute_match_phases(
        match_external_id=1, home_team_id=10, away_team_id=20,
        home_shots=home, away_shots=away,
        home_passes=[], away_passes=[],
        home_def_actions=[], away_def_actions=[],
    )
    home_first = r.value.home_phases[0]
    away_second = r.value.away_phases[1]
    assert home_first.shots_count == 1
    assert away_second.shots_count == 1


# --------------------------------------------------------------------------- #
# Score state
# --------------------------------------------------------------------------- #


def test_score_state_aggregates_per_state():
    leading = [_shot(20), _shot(30)]
    drawing = [_shot(40)]
    trailing = [_shot(60), _shot(75), _shot(85)]
    r = compute_score_state_effects(
        team_external_id=10,
        shots_when_leading=leading,
        shots_when_drawing=drawing,
        shots_when_trailing=trailing,
        matches_analyzed=15,
    )
    assert r.value.leading.shots_count == 2
    assert r.value.drawing.shots_count == 1
    assert r.value.trailing.shots_count == 3
    assert r.value.matches_analyzed == 15


def test_score_state_audit_records_state_xg():
    r = compute_score_state_effects(
        team_external_id=10, shots_when_leading=[],
        shots_when_drawing=[], shots_when_trailing=[],
        matches_analyzed=0,
    )
    assert r.audit.engine == "engine.match_phase"
    assert "leading_xg" in r.audit.value
    assert "drawing_xg" in r.audit.value
    assert "trailing_xg" in r.audit.value
