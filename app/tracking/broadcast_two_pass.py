"""Gündüz yayın takibi, iki geçiş: maç sonrası çözümleme için tek giriş noktası. Canlıda çalışmaz.

Kör kontrolü geçen yöntem (docs/measurements/broadcast-track-round4-control-result.json):

1. Filtreli geçiş: çekim ayırıcı ve tekrar izleyici açık. Duruşlardan maçın kamera konumu bulunur.
2. Filtresiz geçiş: çapa reddedince kamera önseli ikinci kararı verir.
3. Bekçi: kameradan dönme+zoom ile açıklanmayan duruş üretilmemiş sayılır.

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


def track_two_pass(frames: Callable[[], Frames], fps: float = 15.0) -> TwoPassTrack:
    """`frames` her çağrıda videoyu baştan, (kare no, BGR) olarak ve sabit `fps` ile verir."""
    first = BackfillingTracker(fps)
    seen: dict[int, np.ndarray] = {}
    size = (0, 0)
    for k, bgr in frames():
        size = (bgr.shape[1], bgr.shape[0])
        for done_k, result in first.feed(k, bgr):
            if result.homography is not None and done_k % CAMERA_EVERY_FRAMES == 0:
                seen[done_k] = result.homography
    camera = locate_camera([seen[k] for k in sorted(seen)], size)
    if camera is None:
        return TwoPassTrack(None, size)
    prior = CameraPriorAnchor(camera, size)
    second = BackfillingTracker(fps, filters=False, anchor=prior)
    track = TwoPassTrack(camera, size, anchor_sources=prior.stats)
    for k, bgr in frames():
        for done_k, result in second.feed(k, bgr):
            track.states[result.state] += 1
            if result.homography is None:
                continue
            if explained_by_camera(result.homography, camera, size):
                track.poses[done_k] = result.homography
            else:
                track.guard_rejected += 1
    return track
