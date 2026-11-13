"""Replay tespiti — canlı zaman çizgisini bozan kareleri ayıkla.

Kapsam: farklı açıdan gelen tekrarlar zaten kalibrasyon kapılarınca reddediliyor
(takip kopuyor). Buradaki hedef ANA KAMERADAN gelen AĞIR ÇEKİM tekrar — aynı açı
olduğu için sorunsuz kalibre olup canlı dakikayla kaydediliyor.

Asıl tasarım kararı: ağır çekim TEK BAŞINA yeterli değil. Oyun durunca da
hareket düşer; skorboard yerindeyse kare canlıdır. Şüphede canlı sayılır —
yanlışlıkla tekrarı canlı saymak zaman çizgisini bozar ama tekrar tespiti
sezgiseldir ve gerçek yayınla ayarlanmadan agresif davranmamalı.
"""
from __future__ import annotations

import numpy as np

from app.tracking.replay import (
    ReplayFilter,
    ReplayThresholds,
    classify_frame,
    find_overlay_mask,
    live_motion_baseline,
    overlay_change_ratio,
)


def test_baseline_uses_median_not_mean() -> None:
    """Tek bir hızlı çevirme ortalamayı çeker; sonraki her kare 'yavaş' görünürdü."""
    motions = [10.0] * 20 + [400.0]
    assert live_motion_baseline(motions) == 10.0


def test_baseline_refuses_thin_history() -> None:
    """Referans yoksa 'yavaş' tanımsızdır."""
    assert live_motion_baseline([10.0, 11.0]) is None


def test_slow_motion_alone_is_not_a_replay() -> None:
    """Oyun durmuş olabilir. Skorboard yerindeyse kare CANLIDIR."""
    v = classify_frame(motion=2.0, baseline=20.0, overlay_change=0.01)
    assert v.slow_motion is True
    assert v.is_replay is False
    assert "oyun durmuş olabilir" in v.reason


def test_overlay_disappearance_marks_replay() -> None:
    """Yayıncılar tekrarda skor bindirmesini gizler — bu güçlü işaret."""
    v = classify_frame(motion=3.0, baseline=20.0, overlay_change=0.8)
    assert v.is_replay and v.overlay_gone and v.slow_motion
    assert "skorboard" in v.reason


def test_normal_live_frame_is_clean() -> None:
    v = classify_frame(motion=18.0, baseline=20.0, overlay_change=0.02)
    assert not v.is_replay and not v.slow_motion and not v.overlay_gone
    assert v.reason == ""


def test_missing_signals_default_to_live() -> None:
    """Referans ya da bindirme bulunamadıysa kare atılmaz."""
    assert classify_frame(motion=1.0, baseline=None, overlay_change=None).is_replay is False
    assert classify_frame(motion=1.0, baseline=20.0, overlay_change=None).is_replay is False


def test_thresholds_are_tunable() -> None:
    """Eşikler gerçek yayınla ayarlanacak — sabit gömülü olmamalı."""
    strict = ReplayThresholds(overlay_change_ratio=0.9)
    v = classify_frame(motion=3.0, baseline=20.0, overlay_change=0.5, thresholds=strict)
    assert not v.is_replay


def test_overlay_mask_finds_the_static_region() -> None:
    """Bindirme = zamanla DEĞİŞMEYEN pikseller; nerede olduğunu bilmemize gerek yok."""
    rng = np.random.default_rng(0)
    frames = rng.integers(0, 255, size=(20, 40, 60)).astype(np.float32)
    frames[:, 0:6, 0:20] = 200.0          # sabit "skorboard" köşesi
    mask = find_overlay_mask(frames)
    assert mask is not None
    assert mask[2, 5] and not mask[30, 40]
    assert 0.01 < mask.mean() < 0.2


def test_overlay_mask_refuses_when_everything_is_static() -> None:
    """Tüm kare sabitse (donmuş görüntü) bu bindirme değildir."""
    frames = np.full((20, 40, 60), 100.0, dtype=np.float32)
    assert find_overlay_mask(frames) is None


def test_overlay_change_ratio_detects_removal() -> None:
    rng = np.random.default_rng(1)
    frames = rng.integers(0, 255, size=(20, 40, 60)).astype(np.float32)
    frames[:, 0:6, 0:20] = 200.0
    mask = find_overlay_mask(frames)
    reference = frames[0]

    same = overlay_change_ratio(frames[1], reference, mask)
    assert same is not None and same < 0.2

    removed = frames[1].copy()
    removed[0:6, 0:20] = 20.0             # bindirme kalktı
    gone = overlay_change_ratio(removed, reference, mask)
    assert gone is not None and gone > 0.8


def test_overlay_change_is_none_without_mask() -> None:
    assert overlay_change_ratio(np.zeros((4, 4)), np.zeros((4, 4)), None) is None


# --- ReplayFilter: akış halinde ayıklama ------------------------------------ #

BOOT = 16


def _live_frames(n: int, *, seed: int = 0, overlay: float = 200.0):
    """Canlı akış taklidi: değişen saha + SABİT skorboard köşesi."""
    rng = np.random.default_rng(seed)
    frames = rng.integers(0, 255, size=(n, 40, 60)).astype(np.float32)
    frames[:, 0:6, 0:20] = overlay
    return frames


def test_bootstrap_frames_are_never_dropped() -> None:
    """Isınma sırasında referans yok — hiçbir kare atılamaz.

    Yayınlar canlı başlar; referans olmadan "yavaş" da "bindirme kalktı" da
    tanımsızdır. Bu dönemde kare atmak veri kaybından başka bir şey değildir.
    """
    f = ReplayFilter(bootstrap=BOOT)
    frames = _live_frames(BOOT)
    for g in frames:
        assert f.update(g, motion=0.0).is_replay is False
    assert f.replays == 0
    assert f.frames_seen == BOOT


def test_without_an_overlay_nothing_is_ever_a_replay() -> None:
    """Süzgecin BAŞARISIZLIĞI veri kaybına değil, süzmemeye yol açmalı.

    Yayıncı skorboard göstermiyorsa maske bulunamaz. O durumda ağır çekim tek
    başına tekrar sayılmaz — oyun durunca da hareket düşer.
    """
    rng = np.random.default_rng(3)
    frames = rng.integers(0, 255, size=(BOOT + 10, 40, 60)).astype(np.float32)
    f = ReplayFilter(bootstrap=BOOT)
    for g in frames[:BOOT]:
        f.update(g, motion=20.0)
    assert f.mask_found is False
    for g in frames[BOOT:]:
        assert f.update(g, motion=0.5).is_replay is False   # çok yavaş, yine de canlı
    assert f.replays == 0


def test_overlay_disappearance_is_caught_after_bootstrap() -> None:
    """Isınma bitince skorboardın kalkması tekrar olarak yakalanmalı."""
    f = ReplayFilter(bootstrap=BOOT)
    for g in _live_frames(BOOT):
        f.update(g, motion=20.0)
    assert f.mask_found is True

    canli = _live_frames(1, seed=9)[0]
    assert f.update(canli, motion=20.0).is_replay is False

    tekrar = _live_frames(1, seed=9)[0].copy()
    tekrar[0:6, 0:20] = 20.0                    # bindirme kalktı
    v = f.update(tekrar, motion=2.0)            # ağır çekim
    assert v.is_replay and v.overlay_gone
    assert f.replays == 1


def test_replay_frames_do_not_poison_the_live_baseline() -> None:
    """Tekrar kareleri canlı medyanı beslememeli — yoksa süzgeç kendini kör eder.

    Tekrarlar yavaştır. Medyana katılırlarsa medyan düşer, sonraki gerçek
    tekrarlar "yavaş değil" görünür ve süzgeç işlemez hale gelir.
    """
    f = ReplayFilter(bootstrap=BOOT)
    for g in _live_frames(BOOT):
        f.update(g, motion=20.0)
    onceki = list(f._motions)

    tekrar = _live_frames(1, seed=5)[0].copy()
    tekrar[0:6, 0:20] = 20.0
    assert f.update(tekrar, motion=1.0).is_replay
    assert f._motions == onceki, "tekrar karesi medyana katılmamalı"

    canli = _live_frames(1, seed=5)[0]
    f.update(canli, motion=21.0)
    assert f._motions[-1] == 21.0, "canlı kare medyana katılmalı"
