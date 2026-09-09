"""engine.tracking — takım şekli / pres / yerleşim (pozisyon karelerinden)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain import PlayerPosition, TrackingFrame
from app.engine.tracking.compute import (
    _lines_by_x_gap,
    _strip_isolated_keeper,
    compute_formation,
    compute_pressure,
    compute_team_shape,
)

HOME, AWAY = 11, 22


def _p(pid: int, x_m: float, y_m: float, team: int, keeper: bool = False) -> PlayerPosition:
    return PlayerPosition(
        player_external_id=pid, x=x_m / 105 * 100, y=y_m / 68 * 100,
        team_external_id=team, is_keeper=keeper, identity_estimated=True,
    )


def _frame(i: int, players: list[PlayerPosition], ball: tuple[float, float] | None, possession: int | None) -> TrackingFrame:
    return TrackingFrame(
        sport="football", match_external_id=1,
        timestamp=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=i),
        period=1, minute=i / 60, players=tuple(players),
        ball=PlayerPosition(player_external_id=0, x=ball[0] / 105 * 100, y=ball[1] / 68 * 100) if ball else None,
        possession_team_external_id=possession, source="video_tracking",
    )


def _433(team: int, x0: float = 20.0) -> list[PlayerPosition]:
    """Kaleci + 4-3-3 — x hatları 8 m aralıkla, y'de yayılmış."""
    pts = [(x0 - 12, 34)]                                   # GK (izole)
    pts += [(x0, y) for y in (10, 26, 42, 58)]              # 4
    pts += [(x0 + 12, y) for y in (20, 34, 48)]             # 3
    pts += [(x0 + 24, y) for y in (14, 34, 54)]             # 3
    return [_p(100 + i, x, y, team) for i, (x, y) in enumerate(pts)]


def test_lines_by_gap_and_keeper_strip() -> None:
    xs = [8, 20, 20, 20, 20, 32, 32, 32, 44, 44, 44]
    counts = _lines_by_x_gap(xs, 6.0)
    assert counts == [1, 4, 3, 3]
    assert _strip_isolated_keeper(counts, 11) == [4, 3, 3]
    assert _strip_isolated_keeper([4, 3, 3], 10) == [4, 3, 3]
    assert _strip_isolated_keeper([1, 4], 5) == [1, 4]     # az oyuncu → dokunma


def test_team_shape_measures_width_depth_and_formation() -> None:
    frames = [_frame(i, _433(HOME) + _433(AWAY, x0=70.0), (50, 34), HOME) for i in range(5)]
    r = compute_team_shape(HOME, frames)
    v = r.value
    assert v.frames_used == 5 and v.players_mean == 11.0
    assert v.width_m == pytest.approx(48.0, abs=0.2)     # y 10..58
    assert v.depth_m == pytest.approx(36.0, abs=0.2)     # x 8..44
    assert v.formation == "4-3-3" and v.formation_support == 1.0
    assert 0 < v.compactness_m < 30
    assert v.rear_line_x < v.centroid_x < v.front_line_x
    assert r.audit.metric == "team_shape" and r.audit.subject_id == HOME
    assert compute_formation(HOME, frames).value.formation == "4-3-3"


def test_team_shape_empty_when_team_absent() -> None:
    frames = [_frame(0, _433(HOME), None, None)]
    v = compute_team_shape(AWAY, frames).value
    assert v.frames_used == 0 and v.formation is None


def test_pressure_counts_only_opponent_possession_frames() -> None:
    # Top 50,34'te; HOME'un iki oyuncusu 3 m ve 4 m'de, biri 20 m'de
    home = [_p(1, 47, 34, HOME), _p(2, 50, 38, HOME), _p(3, 70, 34, HOME)]
    away = [_p(9, 52, 34, AWAY)]
    f_opp = _frame(0, home + away, (50, 34), AWAY)     # rakip topta → sayılır
    f_own = _frame(1, home + away, (50, 34), HOME)     # kendi topu → sayılmaz
    f_noball = _frame(2, home + away, None, AWAY)      # top yok → sayılmaz
    v = compute_pressure(HOME, [f_opp, f_own, f_noball]).value
    assert v.frames_used == 1
    assert v.nearest_mean_m == 3.0
    assert v.within_5m_mean == 2.0
    assert 0.6 <= v.press_index <= 0.9
    assert compute_pressure(HOME, [f_own]).value.frames_used == 0
