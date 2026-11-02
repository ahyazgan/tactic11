"""Çekim süzgeci: tekrar durum makinesi cv2'siz, kare sınıflandırma sentetik karelerle."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.shot_filter import MAX_REPLAY_S, ReplayTracker, classify_shot, red_ratio

STEP = 0.2
GRASS_BGR = (40, 140, 40)


def feed(tracker: ReplayTracker, start: float, seconds: float, ratio: float) -> list[bool]:
    return [tracker.update(start + i * STEP, ratio) for i in range(round(seconds / STEP))]


def test_wipe_pair_opens_and_closes_replay() -> None:
    t = ReplayTracker()
    assert not any(feed(t, 0.0, 2.0, 0.0))
    assert all(feed(t, 2.0, 0.6, 0.3))
    assert all(feed(t, 2.6, 10.0, 0.0))
    assert all(feed(t, 12.6, 0.6, 0.3))
    assert not any(feed(t, 13.2, 2.0, 0.0))


def test_long_red_run_is_not_a_wipe() -> None:
    t = ReplayTracker()
    feed(t, 0.0, 3.0, 0.3)
    assert not any(feed(t, 3.0, 2.0, 0.0))


def test_faint_red_is_not_a_wipe() -> None:
    t = ReplayTracker()
    feed(t, 0.0, 0.6, 0.1)
    assert not any(feed(t, 0.6, 2.0, 0.0))


def test_missed_closing_wipe_times_out() -> None:
    t = ReplayTracker()
    feed(t, 0.0, 0.6, 0.3)
    assert t.update(MAX_REPLAY_S - 1.0, 0.0) is True
    assert t.update(MAX_REPLAY_S + 1.0, 0.0) is False


def test_classify_wide_view_and_close_up() -> None:
    pytest.importorskip("cv2")
    wide = np.full((1080, 1920, 3), GRASS_BGR, np.uint8)
    wide[:120] = (90, 60, 60)            # tribün
    wide[500:560, 900:920] = (240, 240, 240)  # küçük oyuncu
    assert classify_shot(wide).is_main

    close = wide.copy()
    close[300:1000, 700:1200] = (30, 30, 200)  # kareyi dolduran oyuncu
    verdict = classify_shot(close)
    assert not verdict.is_main and verdict.reason in {"nesne uzun", "nesne büyük"}

    stands = np.full((1080, 1920, 3), (90, 60, 60), np.uint8)
    assert classify_shot(stands).reason == "çim az"


def test_red_ratio_sees_saturated_red_only() -> None:
    pytest.importorskip("cv2")
    frame = np.full((1080, 1920, 3), GRASS_BGR, np.uint8)
    assert red_ratio(frame) == 0.0
    frame[:540] = (0, 0, 230)
    assert red_ratio(frame) == pytest.approx(0.5, abs=0.02)
