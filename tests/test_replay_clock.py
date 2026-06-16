"""replay_clock — event-zaman güdümlü replay saati (saf, determinist).

advance_minute, wall-clock OKUMAZ → sentetik elapsed_wall enjekte edilir.
"""
from __future__ import annotations

from app.engine.replay_clock import ClockConfig, advance_minute, current_phase


def test_linear_mapping_from_elapsed() -> None:
    # interval=10sn, speed=5 → 10sn'de +5 dk, 20sn'de +10 dk.
    cfg = ClockConfig(speed=5.0)
    minute, ended = advance_minute(
        elapsed_wall=10.0, interval=10.0, last_event_minute=90.0, config=cfg,
    )
    assert minute == 5.0
    assert ended is False
    minute2, _ = advance_minute(
        elapsed_wall=20.0, interval=10.0, last_event_minute=90.0, config=cfg,
    )
    assert minute2 == 10.0


def test_ends_at_last_event_not_ninety() -> None:
    # Son event 63'te → 63'ü geçince biter, düz 90 beklenmez.
    cfg = ClockConfig(speed=5.0)
    minute, ended = advance_minute(
        elapsed_wall=200.0, interval=10.0, last_event_minute=63.0, config=cfg,
    )
    assert minute == 63.0
    assert ended is True


def test_speed_multiplier() -> None:
    fast = ClockConfig(speed=10.0)
    minute, _ = advance_minute(
        elapsed_wall=10.0, interval=10.0, last_event_minute=90.0, config=fast,
    )
    assert minute == 10.0


def test_halftime_pause_holds_at_45() -> None:
    # speed=5, interval=10. 45'e 90sn'de varılır (45/5*10). Pause=2 tick →
    # 45'i geçen ham dakika, 2*5=10 dk'lık pause süresince 45'te tutulur.
    cfg = ClockConfig(speed=5.0, halftime_pause_ticks=2)
    # raw at 100sn = 50; pause penceresi içinde (45..55) → 45'te tutulur.
    minute, _ = advance_minute(
        elapsed_wall=100.0, interval=10.0, last_event_minute=90.0, config=cfg,
    )
    assert minute == 45.0
    # raw at 130sn = 65; pause sonrası (65-10=55).
    minute2, _ = advance_minute(
        elapsed_wall=130.0, interval=10.0, last_event_minute=90.0, config=cfg,
    )
    assert minute2 == 55.0


def test_current_phase_boundaries() -> None:
    assert current_phase(10.0) == "1H"
    assert current_phase(45.0) == "1H"
    assert current_phase(60.0) == "2H"
    assert current_phase(75.0) == "closing"
    assert current_phase(88.0) == "closing"
    assert current_phase(90.0) == "FT"
