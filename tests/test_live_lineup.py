"""live_lineup — as-of saha-içi oyuncu çözümleme (Faz B, saf motor).

Kusur #3 düzeltmesini doğrular: sonradan giren/çıkan oyuncunun gerçek dakikası +
verilen dakikada sahadaki oyuncu kümesi.
"""
from __future__ import annotations

from app.engine.live_lineup import (
    PlayerAppearance,
    is_on_pitch,
    minutes_played_as_of,
    resolve_on_pitch,
)

TEAM_A = 100
TEAM_B = 200


def _starter(pid: int, team: int = TEAM_A) -> PlayerAppearance:
    return PlayerAppearance(pid, team, start_minute=0.0, end_minute=None)


def test_starter_minutes_equal_current_minute() -> None:
    app = _starter(7)
    assert minutes_played_as_of(app, 60.0) == 60.0
    assert is_on_pitch(app, 60.0) is True


def test_subbed_off_player_minutes_frozen_and_off_pitch() -> None:
    # 7 numara 60'ta çıktı: 75. dk'da 60 dk oynamış ve sahada DEĞİL.
    app = PlayerAppearance(7, TEAM_A, start_minute=0.0, end_minute=60.0)
    assert minutes_played_as_of(app, 75.0) == 60.0
    assert is_on_pitch(app, 75.0) is False
    # Çıkıştan önce hâlâ sahada ve dakikası artıyor.
    assert minutes_played_as_of(app, 30.0) == 30.0
    assert is_on_pitch(app, 30.0) is True


def test_substitute_not_on_pitch_before_entry() -> None:
    # 19 numara 60'ta girdi: 50. dk'da 0 dk ve sahada değil; 75'te 15 dk.
    app = PlayerAppearance(19, TEAM_A, start_minute=60.0, end_minute=None)
    assert minutes_played_as_of(app, 50.0) == 0.0
    assert is_on_pitch(app, 50.0) is False
    assert minutes_played_as_of(app, 75.0) == 15.0
    assert is_on_pitch(app, 75.0) is True


def test_entry_minute_on_pitch_with_zero_minutes() -> None:
    app = PlayerAppearance(19, TEAM_A, start_minute=60.0)
    assert is_on_pitch(app, 60.0) is True
    assert minutes_played_as_of(app, 60.0) == 0.0


def test_resolve_on_pitch_after_one_sub() -> None:
    # 7 çıktı (0→60), 19 girdi (60→), 10 baştan beri oynuyor.
    apps = [
        PlayerAppearance(7, TEAM_A, 0.0, 60.0),
        PlayerAppearance(19, TEAM_A, 60.0, None),
        PlayerAppearance(10, TEAM_A, 0.0, None),
    ]
    on = resolve_on_pitch(apps, 75.0)
    assert on.player_ids == frozenset({19, 10})        # 7 çıktı
    assert on.minutes_by_player == {7: 60.0, 19: 15.0, 10: 75.0}


def test_resolve_filters_by_team() -> None:
    apps = [
        PlayerAppearance(1, TEAM_A, 0.0, None),
        PlayerAppearance(2, TEAM_B, 0.0, None),
    ]
    on = resolve_on_pitch(apps, 30.0, team_external_id=TEAM_A)
    assert on.player_ids == frozenset({1})
    assert 2 not in on.minutes_by_player


def test_zero_minute_player_excluded_from_minutes_map() -> None:
    # Henüz girmemiş oyuncu minutes_by_player'a girmez.
    apps = [PlayerAppearance(19, TEAM_A, 60.0, None)]
    on = resolve_on_pitch(apps, 50.0)
    assert on.player_ids == frozenset()
    assert on.minutes_by_player == {}
