"""Set-piece Opportunity — H.1 standart top fırsat sinyali."""
from __future__ import annotations

from app.domain import FoulEvent, PassEvent, Shot
from app.engine.set_piece_opportunity import compute_set_piece_opportunity


def _corner(team: int, minute: float, player: int = 1) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1, player_external_id=player,
        team_external_id=team, minute=minute, period=2,
        start_x=99, start_y=0, end_x=88, end_y=50,
        pass_type="corner",
    )


def _fk_off(team: int, minute: float, x: float = 75, player: int = 1) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1, player_external_id=player,
        team_external_id=team, minute=minute, period=2,
        start_x=x, start_y=50, end_x=85, end_y=50,
        pass_type="free_kick",
    )


def _foul(team: int, minute: float, x: float = 75, player: int = 1) -> FoulEvent:
    return FoulEvent(
        sport="football", match_external_id=1, player_external_id=player,
        team_external_id=team, minute=minute, period=2, x=x, y=50,
    )


def _sp_shot(team: int, minute: float, pattern: str = "corner_kick") -> Shot:
    return Shot(
        sport="football", match_external_id=1, player_external_id=9,
        team_external_id=team, minute=minute, x=92, y=50,
        body_part="head",
        pattern=pattern,  # type: ignore[arg-type]
    )


def test_empty_returns_no_set_piece_advice():
    r = compute_set_piece_opportunity(
        11, current_minute=70.0,
    ).value
    assert r.total_set_pieces == 0
    assert "Set-piece yok" in r.tactical_advice


def test_counts_corners_in_window():
    passes = [_corner(11, 50.0), _corner(11, 60.0), _corner(11, 65.0)]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0, passes=passes,
    ).value
    # 50 ≥ 50 lo, 60 ve 65 hepsi window
    assert r.corners_won == 3


def test_excludes_opponent_corners():
    passes = [_corner(22, 60.0), _corner(22, 65.0)]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0, passes=passes,
    ).value
    assert r.corners_won == 0


def test_offensive_free_kick_only_counted_in_attacking_third():
    passes = [
        _fk_off(11, 60.0, x=75),  # ofansif ✓
        _fk_off(11, 65.0, x=40),  # orta saha ✗
        _fk_off(11, 68.0, x=90),  # ofansif ✓
    ]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0, passes=passes,
    ).value
    assert r.free_kicks_won_offensive == 2


def test_fouls_drawn_in_attacking_third():
    """Rakip ofansif bölgemizde faul yaptı → biz lehte set-piece kazandık."""
    fouls = [
        _foul(22, 60.0, x=75),
        _foul(22, 65.0, x=85),
        _foul(22, 68.0, x=40),  # orta saha — sayılmaz
        _foul(11, 62.0, x=75),  # bizim faul — sayılmaz
    ]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0,
        fouls=fouls, opponent_external_id=22,
    ).value
    assert r.fouls_drawn_offensive == 2


def test_high_frequency_low_conversion_triggers_change_routine():
    """5 set-piece + 0 şut → high freq + low conv → 'rutin değiştir'."""
    passes = [_corner(11, 60.0 + i) for i in range(5)]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0, passes=passes,
    ).value
    assert r.total_set_pieces == 5
    assert r.set_piece_shots == 0
    assert r.high_frequency is True
    assert r.low_conversion is True
    assert "rutin değiştir" in r.tactical_advice.lower()


def test_normal_conversion_advice_neutral():
    """3 set-piece + 2 şut → conversion 0.67 → normal akış."""
    passes = [_corner(11, 60.0), _corner(11, 62.0), _corner(11, 65.0)]
    shots = [_sp_shot(11, 61.0), _sp_shot(11, 66.0)]
    r = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0,
        passes=passes, shots=shots,
    ).value
    assert r.high_frequency is True
    assert r.low_conversion is False
    assert "rutin değiştir" not in r.tactical_advice.lower()


def test_audit_complete():
    res = compute_set_piece_opportunity(
        11, current_minute=70.0, window_min=20.0,
        passes=[_corner(11, 65.0)],
    )
    a = res.audit.value
    assert "total_set_pieces" in a
    assert "conversion_to_shot_pct" in a
    assert "tactical_advice" in a
