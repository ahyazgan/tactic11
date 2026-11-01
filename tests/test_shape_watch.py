"""Savunma şekli bekçisi: kare örneği, normal-şimdi farkı, mesaj yönü."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain import PlayerPosition, TrackingFrame
from app.engine.shape_watch import compute_shape_watch, sample_frame

HOME, AWAY = 11, 22
L, W = 105.0, 68.0


def _pos(pid: int, team: int, x_m: float, y_m: float, keeper: bool = False) -> PlayerPosition:
    return PlayerPosition(player_external_id=pid, team_external_id=team, x=x_m / L * 100, y=y_m / W * 100,
                          is_keeper=keeper)


def _home_defending(minute: float, back: float, gap: float, width: float, period: int = 1) -> TrackingFrame:
    """Ev sahibi (+x'e hücum eder, kalesi x=0) savunuyor: 4-4-2 blok."""
    ys4 = [34 - width / 2, 34 - width / 6, 34 + width / 6, 34 + width / 2]
    players = [_pos(1, HOME, 2, 34)]  # kaleci: izole en derin
    players += [_pos(10 + i, HOME, back, y) for i, y in enumerate(ys4)]
    players += [_pos(20 + i, HOME, back + gap, y) for i, y in enumerate(ys4)]
    players += [_pos(30, HOME, back + gap + 12, 30), _pos(31, HOME, back + gap + 12, 38)]
    # rakip: kalecisi x=103, oyuncuları ev sahibi yarısına yakın
    players += [_pos(100, AWAY, 103, 34)] + [_pos(101 + i, AWAY, back + 5 + 3 * i, 10 + 5 * i) for i in range(8)]
    return TrackingFrame(sport="football", match_external_id=9, timestamp=datetime.now(UTC), period=period,
                         minute=minute, players=tuple(players), possession_team_external_id=AWAY)


def test_sample_frame_measures_defending_shape() -> None:
    s = sample_frame(_home_defending(10, back=30, gap=10, width=40), HOME, direction=1)
    assert s is not None
    assert s.block_depth == 30 and s.line_gap == 10 and s.width == 40
    assert s.length == 22 and s.players == 10


def test_sample_frame_mirrors_when_attacking_minus_x() -> None:
    f = _home_defending(10, back=30, gap=10, width=40)
    mirrored = f.model_copy(update={"players": tuple(
        p.model_copy(update={"x": 100 - p.x}) for p in f.players)})
    s = sample_frame(mirrored, HOME, direction=-1)
    assert s is not None and abs(s.block_depth - 30) < 1e-6


def test_sample_frame_abstains_on_too_few_or_unknown_direction() -> None:
    f = _home_defending(10, back=30, gap=10, width=40)
    assert sample_frame(f, HOME, direction=0) is None
    few = f.model_copy(update={"players": f.players[:4]})
    assert sample_frame(few, HOME, direction=1) is None


def _frames(recent_back: float, recent_gap: float = 10.0) -> list[TrackingFrame]:
    out = []
    t = 0.0
    while t <= 30.0:
        recent = t >= 25.0
        out.append(_home_defending(t, back=recent_back if recent else 36.0, gap=recent_gap if recent else 10.0,
                                   width=40))
        t += 0.1
    return out


def test_dropping_block_raises_warning_for_us() -> None:
    rep = compute_shape_watch(_frames(recent_back=28.0), home_team_external_id=HOME, away_team_external_id=AWAY,
                              my_team_external_id=HOME, minute=30.0).value
    home = rep.teams[0]
    assert home.metrics["block_depth"].baseline == 36.0 and home.metrics["block_depth"].recent == 28.0
    assert [(f.metric, f.severity, f.ours) for f in rep.findings] == [("block_depth", "warning", True)]
    assert rep.findings[0].message.startswith("Savunma bloğumuz 8 m geriledi (36 → 28 m)")


def test_same_change_reads_as_opportunity_when_it_is_the_opponent() -> None:
    rep = compute_shape_watch(_frames(recent_back=28.0, recent_gap=16.0), home_team_external_id=HOME,
                              away_team_external_id=AWAY, my_team_external_id=AWAY, minute=30.0).value
    metrics = {f.metric for f in rep.findings}
    assert metrics == {"block_depth", "line_gap", "length"}  # açılan hat aralığı takımı da uzatır
    assert all(not f.ours and f.severity == "info" for f in rep.findings)
    assert any("araya pas" in f.message for f in rep.findings)


def test_small_change_and_thin_windows_stay_silent() -> None:
    rep = compute_shape_watch(_frames(recent_back=33.0), home_team_external_id=HOME, away_team_external_id=AWAY,
                              my_team_external_id=HOME, minute=30.0).value
    assert rep.findings == []
    thin = [f for f in _frames(recent_back=20.0) if f.minute < 25.0 or f.minute > 29.5]
    rep2 = compute_shape_watch(thin, home_team_external_id=HOME, away_team_external_id=AWAY,
                               my_team_external_id=HOME, minute=30.0).value
    assert rep2.findings == [] and rep2.teams[0].recent_samples < 20


def test_frames_without_possession_are_not_counted() -> None:
    frames = [f.model_copy(update={"possession_team_external_id": None}) for f in _frames(28.0)]
    rep = compute_shape_watch(frames, home_team_external_id=HOME, away_team_external_id=AWAY,
                              my_team_external_id=HOME, minute=30.0).value
    assert rep.teams[0].baseline_samples == 0 and rep.findings == []
