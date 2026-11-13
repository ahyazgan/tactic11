"""Tekrar süzgecinin eskiyen referansı yeniden öğrenen ürün sürümü (venv-cv).

Neden ayrı modül: `app/tracking/replay.py` ve `pipeline.py` kör kontroller için hash'le
dondurulmuş ölçüm kodudur (`docs/measurements/*frozen-decision.json`,
`tests/test_guarded_control.py`). Bu davranış onlara yazılamaz; ürün işçisi
(`scripts/track_video_product.py`) çalışırken `install()` ile bağlar. Ölçüm betikleri
`scripts.track_video` üzerinden dondurulmuş süzgeçle çalışmayı sürdürür.

Düzelttiği kusur: kalıcı olarak kalkan bir yazı (açılış altyazısı) referansta kalınca maçın
geri kalanı "bindirme kalkmış" görünür ve tekrar diye atılır. Ölçüldü: 94 dakikalık videoda
83. kareden sonra 27 bin kare ardı ardına atıldı
(`docs/measurements/product-full-match-exam-result.json`).
"""
from __future__ import annotations

from typing import Any

from app.tracking.replay import ReplayFilter, ReplayVerdict

# Bindirme bu kadar ardışık karede "kalkmış" görünüyorsa tekrar değildir: tekrar saniyeler
# sürer. Referans eskimiştir ve süzgeç yeniden ısınır. 15 fps'te 900 kare = 60 sn; gerçek
# yayınla ayarlanmadı.
MAX_REPLAY_RUN_FRAMES = 900


class RelearningReplayFilter(ReplayFilter):
    """`ReplayFilter` + sınır: `max_replay_run` ardışık tekrardan sonra yeniden ısınır."""

    def __init__(self, *, max_replay_run: int = MAX_REPLAY_RUN_FRAMES, **kwargs: Any):
        super().__init__(**kwargs)
        self._max_run = max_replay_run
        self._run = 0
        self.relearns = 0

    def update(self, gray: Any, motion: float) -> ReplayVerdict:
        verdict = super().update(gray, motion)
        if not verdict.is_replay:
            self._run = 0
            return verdict
        self._run += 1
        if self._run >= self._max_run:
            self._ready = False
            self._mask = self._reference = None
            self._run = 0
            self.relearns += 1
        return verdict


def install() -> None:
    """Bu süreçte `pipeline`'ın kuracağı süzgeci ürün sürümüyle değiştirir.

    `pipeline.collect_observations` süzgeci çağrı anında `app.tracking.replay` modülünden
    alır; ad burada yeniden bağlanır. Yalnız ürün işçisinin kendi sürecinde çağrılır.
    """
    from app.tracking import replay

    setattr(replay, "ReplayFilter", RelearningReplayFilter)  # noqa: B010 — mypy sınıf adına atamayı reddeder
