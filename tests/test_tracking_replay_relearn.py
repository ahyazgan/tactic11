"""Ürün tekrar süzgeci: eskiyen referansı yeniden öğrenir, dondurulmuş süzgeci değiştirmez."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking import replay
from app.tracking.replay_relearn import RelearningReplayFilter, install

BOOT = 16


def _live_frames(n: int, *, seed: int = 0, overlay: float = 200.0):
    """Canlı akış taklidi: değişen saha + SABİT skorboard köşesi."""
    rng = np.random.default_rng(seed)
    frames = rng.integers(0, 255, size=(n, 40, 60)).astype(np.float32)
    frames[:, 0:6, 0:20] = overlay
    return frames


def test_permanently_removed_overlay_does_not_drop_the_rest_of_the_match() -> None:
    """Kalıcı kalkan yazı (açılış altyazısı) maçın kalanını tekrar saydırmamalı.

    Tekrar saniyeler sürer. Bindirme sınırdan uzun süre yoksa referans eskimiştir:
    süzgeç yeniden ısınır ve kareler yeniden canlı sayılır.
    """
    limit = 20
    f = RelearningReplayFilter(bootstrap=BOOT, max_replay_run=limit)
    for g in _live_frames(BOOT):
        f.update(g, motion=20.0)
    yazisiz = np.random.default_rng(5).integers(0, 255, size=(limit + BOOT + 30, 40, 60)).astype(np.float32)
    verdicts = [f.update(g, motion=20.0).is_replay for g in yazisiz]
    assert all(verdicts[:limit])
    assert not any(verdicts[limit:])
    assert f.replays == limit and f.relearns == 1


def test_short_replay_does_not_trigger_relearning() -> None:
    """Sınırdan kısa tekrar gerçek tekrardır: atılır, sonra canlı akış sürer."""
    f = RelearningReplayFilter(bootstrap=BOOT, max_replay_run=20)
    for g in _live_frames(BOOT):
        f.update(g, motion=20.0)
    tekrar = np.random.default_rng(6).integers(0, 255, size=(10, 40, 60)).astype(np.float32)
    assert all(f.update(g, motion=20.0).is_replay for g in tekrar)
    assert f.update(_live_frames(1, seed=7)[0], motion=20.0).is_replay is False
    assert f.relearns == 0 and f.mask_found is True


def test_frozen_filter_keeps_dropping_so_the_two_are_really_different() -> None:
    """Dondurulmuş süzgeç eski davranışta kalır; ürün farkı yalnız `install()` ile gelir."""
    f = replay.ReplayFilter(bootstrap=BOOT)
    for g in _live_frames(BOOT):
        f.update(g, motion=20.0)
    yazisiz = np.random.default_rng(5).integers(0, 255, size=(60, 40, 60)).astype(np.float32)
    assert all(f.update(g, motion=20.0).is_replay for g in yazisiz)


def test_install_rebinds_the_name_the_pipeline_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(replay, "ReplayFilter", replay.ReplayFilter)  # test sonunda geri alınır
    install()
    from app.tracking.replay import ReplayFilter

    assert ReplayFilter is RelearningReplayFilter
