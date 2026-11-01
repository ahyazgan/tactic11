"""Maç saati: devre başlangıcından dakika, devre arası, gecikme çapası, başlama vuruşu."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain import PlayerPosition, TrackingFrame
from app.tracking.match_clock import MatchClock, detect_kickoff, is_kickoff_frame

K1 = datetime(2026, 11, 1, 17, 0, 0, tzinfo=UTC)
K2 = K1 + timedelta(minutes=63)  # 45 + 3 uzatma + 15 devre arası


def test_minutes_follow_real_periods_and_skip_the_break() -> None:
    clock = MatchClock(period_starts=(K1,), delay_s=40.0)
    assert clock.state_at(K1).status == "pre_match"  # yayın 40 sn geride
    s = clock.state_at(K1 + timedelta(seconds=40 + 600))
    assert (s.period, s.minute, s.status) == (1, 10.0, "in_play")
    assert clock.state_at(K1 + timedelta(minutes=47, seconds=40)).minute == 47.0  # uzatma dakikası
    assert clock.state_at(K1 + timedelta(minutes=60)).status == "break"  # 2. yarı henüz bildirilmedi
    clock2 = clock.with_period_starts([K2, K1])
    s2 = clock2.state_at(K2 + timedelta(seconds=40 + 90))
    assert (s2.period, s2.minute) == (2, 46.5)


def test_segment_state_and_round_trip(tmp_path: Path) -> None:
    clock = MatchClock(period_starts=(K1,), stream_started_at=K1 - timedelta(minutes=2), segment_seconds=30)
    assert clock.segment_state(0).status == "pre_match"
    assert clock.segment_state(6).minute == 1.0
    path = tmp_path / "clock.json"
    clock.save(path)
    assert MatchClock.load(path) == clock


def test_anchor_delay_accepts_only_plausible_values() -> None:
    clock = MatchClock(period_starts=(K1, K2))
    anchored = clock.anchor_delay(1, K1 + timedelta(seconds=37))
    assert anchored is not None and anchored.delay_s == 37.0 and anchored.delay_anchored_periods == (1,)
    assert clock.anchor_delay(2, K2 + timedelta(minutes=5)) is None   # 300 sn: makul değil
    assert clock.anchor_delay(3, K2) is None                          # bilinmeyen devre


HOME, AWAY = 1, 2


def _frame(minute: float, kickoff: bool) -> TrackingFrame:
    players = []
    for i in range(8):
        x_home = 40.0 - 4 * i if kickoff else 60.0
        players.append(PlayerPosition(player_external_id=i, team_external_id=HOME,
                                      x=x_home / 105 * 100, y=(8 + 7 * i) / 68 * 100))
        players.append(PlayerPosition(player_external_id=100 + i, team_external_id=AWAY,
                                      x=(65.0 + 4 * i) / 105 * 100, y=(8 + 7 * i) / 68 * 100))
    players.append(PlayerPosition(player_external_id=50, team_external_id=HOME, x=52.0 / 105 * 100,
                                  y=34.0 / 68 * 100))
    return TrackingFrame(sport="football", match_external_id=1, timestamp=K1, period=1, minute=minute,
                         players=tuple(players))


def test_kickoff_frame_needs_both_halves_and_a_centre_player() -> None:
    assert is_kickoff_frame(_frame(0, True), HOME, AWAY)
    assert not is_kickoff_frame(_frame(0, False), HOME, AWAY)  # ev sahibi yarıyı geçmiş


def test_detect_kickoff_returns_last_frame_of_a_stable_run() -> None:
    frames = [_frame(0.01 * i, kickoff=4 <= i <= 9) for i in range(20)]
    hit = detect_kickoff(frames, HOME, AWAY)
    assert hit is not None and abs(hit.minute - 0.09) < 1e-9
    blip = [_frame(0.01 * i, kickoff=i == 4) for i in range(20)]
    assert detect_kickoff(blip, HOME, AWAY) is None


def test_watch_clock_merges_anchor_and_kickoff_anchor(tmp_path: Path) -> None:
    from app.tracking.match_clock import (
        kickoff_anchor,
        load_watch_clock,
        save_anchor,
    )

    assert load_watch_clock(tmp_path) is None
    clock = MatchClock(period_starts=(K1,), stream_started_at=K1, segment_seconds=30)
    clock.save(tmp_path / "clock.json")
    # segment 1 (K1+30 sn), içinde 0.2 dk'da başlama vuruşu dizilişi biter → duvar K1+42 sn
    frames = [_frame(0.5 + 0.01 * i, kickoff=i <= 20) for i in range(40)]
    state = clock.segment_state(1)
    anchored = kickoff_anchor(clock, state, 1, 0.5, frames, HOME, AWAY)
    assert anchored is not None and anchored.delay_s == 42.0
    save_anchor(tmp_path, anchored)
    merged = load_watch_clock(tmp_path)
    assert merged is not None and merged.delay_s == 42.0 and merged.delay_anchored_periods == (1,)
    assert kickoff_anchor(merged, merged.segment_state(1), 1, 0.5, frames, HOME, AWAY) is None  # bir kez
