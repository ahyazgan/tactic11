"""Gündüz yayın takibi, iki geçiş: maç sonrası çözümleme için tek giriş noktası. Canlıda çalışmaz.

Kör kontrolü geçen yöntem (docs/measurements/broadcast-track-round4-control-result.json):

1. Filtreli geçiş: çekim ayırıcı ve tekrar izleyici açık. Duruşlardan maçın kamera konumu bulunur.
2. Filtresiz geçiş: çapa reddedince kamera önseli ikinci kararı verir.
3. Bekçi: kameradan dönme+zoom ile açıklanmayan duruş üretilmemiş sayılır.
4. Tekrar: ilk geçişin tekrar saydığı karede duruş üretilmez. Ana kameradan gösterilen tekrar bekçiden
   geçer (kamera aynıdır); atılmazsa aynı an iki kez konumlanır. İşaret J.League yayınının kırmızı
   logo geçişidir (`shot_filter.ReplayTracker`), başka yayına taşınmaz. Kapanış geçişi görülmeyen
   pencerede (izleyicinin `MAX_REPLAY_S` tavanına dayanan) duruş ATILMAZ: ölçüldü, kırmızı formalı
   yakın çekim kapanış geçişini gizleyince tavana kadar canlı oyun "tekrar" sayılıyor
   (kashima_machida 80–140. sn). O pencere `unclosed_replays` ile ayrıca bildirilir.

Kamera bulunamazsa hiç duruş üretilmez: bekçisiz duruş başka kameradan gelebilir (3. turda other %9,1).
Video iki kez okunur; sınır ve süreler BACKLOG.md'de.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

from app.tracking.broadcast_track import BackfillingTracker
from app.tracking.camera_anchor import CameraPriorAnchor, explained_by_camera, locate_camera
from app.tracking.shot_filter import MAX_REPLAY_S

CAMERA_EVERY_FRAMES = 45   # kamera konumu 3 sn'de bir duruştan bulunur; kontrol koşusundaki örnekleme

Frames = Iterable[tuple[int, np.ndarray]]


@dataclass
class TwoPassTrack:
    camera: np.ndarray | None                     # (x, y, yükseklik) m; None ise duruş üretilmedi
    size: tuple[int, int] = (0, 0)
    poses: dict[int, np.ndarray] = field(default_factory=dict)   # kare no → görüntü→saha
    states: Counter = field(default_factory=Counter)             # ikinci geçişin kare durumları
    anchor_sources: dict[str, int] = field(default_factory=dict)
    guard_rejected: int = 0
    replays: set[int] = field(default_factory=set)               # kapanışı görülen tekrar pencerelerinin kareleri
    unclosed_replays: set[int] = field(default_factory=set)      # tavana dayanan pencereler: duruş atılmaz
    replay_rejected: int = 0                                     # bunlardan duruşu olup atılanlar


def frame_windows(frames: set[int]) -> list[tuple[int, int]]:
    """Ardışık kare numaralarını (ilk, son) pencerelerine toplar."""
    windows: list[tuple[int, int]] = []
    for k in sorted(frames):
        if windows and k == windows[-1][1] + 1:
            windows[-1] = (windows[-1][0], k)
        else:
            windows.append((k, k))
    return windows


def closed_replays(replays: set[int], fps: float) -> tuple[set[int], set[int]]:
    """(kapanışı görülen, görülmeyen) tekrar kareleri. Tavana dayanan pencerenin sonu bir geçiş değildir."""
    closed: set[int] = set()
    unclosed: set[int] = set()
    for a, b in frame_windows(replays):
        (unclosed if (b - a + 1) / fps >= MAX_REPLAY_S else closed).update(range(a, b + 1))
    return closed, unclosed


def track_two_pass(frames: Callable[[], Frames], fps: float = 15.0) -> TwoPassTrack:
    """`frames` her çağrıda videoyu baştan, (kare no, BGR) olarak ve sabit `fps` ile verir."""
    first = BackfillingTracker(fps)
    seen: dict[int, np.ndarray] = {}
    marked: set[int] = set()
    size = (0, 0)
    for k, bgr in frames():
        size = (bgr.shape[1], bgr.shape[0])
        for done_k, result in first.feed(k, bgr):
            if result.state == "replay":
                marked.add(done_k)
            if result.homography is not None and done_k % CAMERA_EVERY_FRAMES == 0:
                seen[done_k] = result.homography
    camera = locate_camera([seen[k] for k in sorted(seen)], size)
    if camera is None:
        return TwoPassTrack(None, size)
    prior = CameraPriorAnchor(camera, size)
    second = BackfillingTracker(fps, filters=False, anchor=prior)
    replays, unclosed = closed_replays(marked, fps)
    track = TwoPassTrack(camera, size, anchor_sources=prior.stats, replays=replays, unclosed_replays=unclosed)
    for k, bgr in frames():
        for done_k, result in second.feed(k, bgr):
            track.states[result.state] += 1
            if result.homography is None:
                continue
            if not explained_by_camera(result.homography, camera, size):
                track.guard_rejected += 1
            elif done_k in replays:
                track.replay_rejected += 1
            else:
                track.poses[done_k] = result.homography
    return track
