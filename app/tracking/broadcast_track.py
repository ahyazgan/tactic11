"""Gündüz yayın takibi: yayın çapasından sonra duruşu görüntü akışı ve çizgilerle taşır.

Üretime bağlı değildir; `pitch_lines.py` hash'li olduğu için ayrı durur. Ölçümler:
docs/measurements/tracking-funnel-daylight.json, ön kayıt:
docs/measurements/broadcast-tracking-preregistration.json.

Duruş akışla taşınır, yerel kontrast çizgileriyle düzeltilir. Kare yalnız çizgi kapısını geçerse
üretilir. Kesme ve tekrar duruşu siler; kapıyı uzun süre geçemeyen duruş da silinir, çünkü
akış tek başına sürüklenir (ölçüldü: 3 sn'de 13 m).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.tracking.broadcast_anchor import daylight_line_mask, find_broadcast_anchor
from app.tracking.homography_fit import DEFAULT_TOLERANCE_PX, refine_homography
from app.tracking.shot_filter import ReplayTracker, classify_shot, red_ratio

FLOW_MAX_CORNERS = 400
FLOW_MIN_INLIERS = 30          # bundan azı süreklilik kanıtı sayılmaz
CUT_MIN_HIST_CORR = 0.7
LINE_GATE = 0.70
SEARCH_STEP_PX = 12.0
MAX_JUMP_M = 5.0               # düzeltme taşınan duruştan bundan fazla oynatamaz
MAX_COAST_FRAMES = 15          # 15 fps'te 1 sn; üretim takibinin COAST_FRAMES değeriyle aynı
ANCHOR_EVERY_FRAMES = 5        # çapa araması pahalı; ama kapsama kaybının çoğu çapa beklerken (ilk koşu)
REPLAY_EVERY_FRAMES = 3        # ReplayTracker 5 fps ile beslenmeli, takip 15 fps koşar
BASE_WIDTH_PX = 1280.0
BACKFILL_FRAMES = 450          # 15 fps'te 30 sn: çapa bulununca geriye bu kadar kare takip edilir
BUFFER_JPEG_QUALITY = 95
# Görüntüden yeniden konumlanma: ana kamera sabit noktada döner, kesmeden sonra aynı görüşe gelir.
# Bırakma sınaması (88 duruşlu örnek): 200 eşleşme altı 5 m üstü sapmayı 5'ten 1'e indiriyor.
RELOC_MIN_INLIERS = 200
RELOC_FEATURES = 2500
RELOC_RATIO = 0.75
RELOC_RANSAC_PX = 3.0
RELOC_EVERY_SEARCHES = 3       # eşleştirme anahtar sayısıyla büyür, her aramada denenmez
KEY_EVERY_FRAMES = 45          # 3 sn
MAX_KEYS = 300
OVERLAY_BOXES = ((0.044, 0.046, 0.284, 0.106), (0.914, 0.875, 0.953, 0.949))   # skor grafiği, yayıncı logosu
BUFFERED_STATES = {"gate", "gate_lost", "searching", "no_anchor", "cut"}


def gray_hist(gray: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.normalize(cv2.calcHist([gray], [0], None, [32], [0, 256]), None).flatten()


def flow_step(prev_gray: np.ndarray, gray: np.ndarray) -> tuple[np.ndarray | None, int, float]:
    """Önceki görüntüden şimdikine homografi. Yayın kamerası dönme+zoom olduğu için tek homografi yeter."""
    import cv2

    pts = cv2.goodFeaturesToTrack(prev_gray, FLOW_MAX_CORNERS, 0.01, 12)
    if pts is None or len(pts) < FLOW_MIN_INLIERS:
        return None, 0, 0.0
    moved, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts, None, winSize=(21, 21), maxLevel=3)
    good = status.ravel() == 1
    if good.sum() < FLOW_MIN_INLIERS:
        return None, int(good.sum()), float(good.mean())
    t, inliers = cv2.findHomography(pts[good], moved[good], cv2.RANSAC, 2.0)
    if t is None or inliers is None:
        return None, 0, 0.0
    count = int(inliers.sum())
    return t, count, count / len(pts)


def is_cut(inliers: int, hist_corr: float) -> bool:
    return inliers < FLOW_MIN_INLIERS or hist_corr < CUT_MIN_HIST_CORR


def distance_map(mask: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.distanceTransform((~mask.astype(bool)).astype(np.uint8), cv2.DIST_L2, 3)


def pose_shift_m(h_a: np.ndarray, h_b: np.ndarray, size: tuple[int, int]) -> float:
    """İki homografinin görüntü merkezindeki ızgarada en büyük saha farkı (m)."""
    w, h = size
    pts = np.array([[w * fx, h * fy, 1.0] for fx in (0.25, 0.5, 0.75) for fy in (0.45, 0.6, 0.75)])
    a, b = pts @ h_a.T, pts @ h_b.T
    return float(np.hypot(*((a[:, :2] / a[:, 2:3]) - (b[:, :2] / b[:, 2:3])).T).max())


def corrected_pose(carried: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Taşınan duruşu çizgilere oturt; kapıyı geçmezse None."""
    height, width = mask.shape[:2]
    tolerance = DEFAULT_TOLERANCE_PX * width / BASE_WIDTH_PX
    fit = refine_homography(carried, distance_map(mask), step_px=SEARCH_STEP_PX, tolerance_px=tolerance)
    if fit.accepted and fit.inlier_ratio >= LINE_GATE and pose_shift_m(fit.homography, carried, (width, height)) <= MAX_JUMP_M:
        return fit.homography, fit.inlier_ratio
    return None


class Relocalizer:
    """Çapadan gelen duruşlu karelerin görüntü özelliklerini tutar, kayıp kareye duruş taşır."""

    def __init__(self) -> None:
        self._orb: Any = None
        self._matcher: Any = None
        self._keys: deque[tuple[np.ndarray, np.ndarray, np.ndarray]] = deque(maxlen=MAX_KEYS)

    def _features(self, gray: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        import cv2

        if self._orb is None:
            self._orb = cv2.ORB_create(RELOC_FEATURES)
            self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        height, width = gray.shape
        mask = np.full(gray.shape, 255, np.uint8)
        for x0, y0, x1, y1 in OVERLAY_BOXES:
            mask[int(y0 * height):int(y1 * height), int(x0 * width):int(x1 * width)] = 0
        points, descriptors = self._orb.detectAndCompute(gray, mask)
        return np.array([kp.pt for kp in points], dtype=np.float32), descriptors

    def add(self, gray: np.ndarray, pose: np.ndarray) -> None:
        points, descriptors = self._features(gray)
        if descriptors is not None:
            self._keys.append((points, descriptors, pose))

    def locate(self, gray: np.ndarray) -> np.ndarray | None:
        """En çok RANSAC eşleşmesi alan anahtarın duruşu bu kareye taşınır; yetersizse None."""
        import cv2

        if not self._keys:
            return None
        points, descriptors = self._features(gray)
        if descriptors is None:
            return None
        best_count, best_pose = 0, None
        for key_points, key_descriptors, pose in self._keys:
            pairs = self._matcher.knnMatch(key_descriptors, descriptors, k=2)
            good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RELOC_RATIO * p[1].distance]
            if len(good) < RELOC_MIN_INLIERS:
                continue
            source = key_points[[m.queryIdx for m in good]]
            target = points[[m.trainIdx for m in good]]
            t, inliers = cv2.findHomography(source, target, cv2.RANSAC, RELOC_RANSAC_PX)
            if t is None or inliers is None:
                continue
            count = int(inliers.sum())
            if count >= RELOC_MIN_INLIERS and count > best_count:
                best_count, best_pose = count, pose @ np.linalg.inv(t)
        return best_pose


@dataclass
class TrackFrame:
    homography: np.ndarray | None   # görüntü → saha; kapıdan geçmeyen karede None
    state: str
    inlier: float = 0.0
    carried: np.ndarray | None = None   # kapıdan geçmeyen karede akışla taşınan duruş
    origin: str = "anchor"              # duruş zinciri çapadan mı yeniden konumlanmadan mı geliyor


class BroadcastTracker:
    """Kareleri zaman sırasıyla ve sabit sıklıkla alır; her kare için duruş ya da neden döner."""

    def __init__(self, fps: float = 15.0, *, filters: bool = True) -> None:
        self._fps = fps
        self._filters = filters         # False: çekim ayırıcı ve tekrar izleyici duruş kesmez (3. tur ön kaydı)
        self._h: np.ndarray | None = None
        self._coast = 0
        self._count = 0
        self._since_search = ANCHOR_EVERY_FRAMES
        self._prev_gray: np.ndarray | None = None
        self._prev_hist: np.ndarray | None = None
        self._replay = ReplayTracker()
        self._in_replay = False
        self._reloc = Relocalizer()
        self._origin = "anchor"
        self._searches = 0

    def _drop(self) -> None:
        self._h = None
        self._coast = 0
        self._since_search = ANCHOR_EVERY_FRAMES

    def _motion(self, gray: np.ndarray, hist: np.ndarray) -> tuple[np.ndarray | None, bool]:
        import cv2

        if self._prev_gray is None or self._prev_hist is None:
            return None, False
        motion, inliers, _ = flow_step(self._prev_gray, gray)
        corr = float(cv2.compareHist(self._prev_hist, hist, cv2.HISTCMP_CORREL))
        return motion, motion is None or is_cut(inliers, corr)

    def step(self, bgr: np.ndarray) -> TrackFrame:
        import cv2

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        hist = gray_hist(gray)
        motion, cut = self._motion(gray, hist)
        self._prev_gray, self._prev_hist = gray, hist
        if self._filters and self._count % REPLAY_EVERY_FRAMES == 0:
            self._in_replay = self._replay.update(self._count / self._fps, red_ratio(bgr))
        self._count += 1
        if cut or self._in_replay:
            self._drop()
            return TrackFrame(None, "replay" if self._in_replay else "cut")
        carried = None if self._h is None or motion is None else self._h @ np.linalg.inv(motion)
        if self._filters and not classify_shot(bgr).is_main:
            return self._coasted(carried, "not_main")
        mask = daylight_line_mask(bgr)
        if carried is None:
            return self._search(mask, gray)
        fit = corrected_pose(carried, mask)
        if fit is not None:
            self._h, self._coast = fit[0], 0
            # Yeniden konumlanma zinciri anahtar üretmez: hata kendi üstüne birikmesin
            if self._origin == "anchor" and self._count % KEY_EVERY_FRAMES == 0:
                self._reloc.add(gray, fit[0])
            return TrackFrame(fit[0], "tracked", fit[1], origin=self._origin)
        return self._coasted(carried, "gate")

    def _coasted(self, carried: np.ndarray | None, state: str) -> TrackFrame:
        if carried is None:
            return TrackFrame(None, state)
        self._coast += 1
        if self._coast > MAX_COAST_FRAMES:
            self._drop()
            return TrackFrame(None, f"{state}_lost")
        self._h = carried
        return TrackFrame(None, state, carried=carried, origin=self._origin)

    def _search(self, mask: np.ndarray, gray: np.ndarray) -> TrackFrame:
        self._since_search += 1
        if self._since_search < ANCHOR_EVERY_FRAMES:
            return TrackFrame(None, "searching")
        self._since_search = 0
        res = find_broadcast_anchor(mask, gray)
        if res.accepted and res.homography is not None:
            self._h, self._coast, self._origin = res.homography, 0, "anchor"
            self._reloc.add(gray, res.homography)
            return TrackFrame(res.homography, "anchored", res.inlier)
        self._searches += 1
        if self._searches % RELOC_EVERY_SEARCHES != 0:
            return TrackFrame(None, "no_anchor")
        located = self._reloc.locate(gray)
        fit = None if located is None else corrected_pose(located, mask)
        if fit is None:
            return TrackFrame(None, "no_anchor")
        self._h, self._coast, self._origin = fit[0], 0, "reloc"
        return TrackFrame(fit[0], "relocalized", fit[1], origin="reloc")


class BackfillingTracker:
    """Çapa bulununca aynı çekimde çapayı bekleyen kareleri geriye doğru da takip eder.

    Maç sonrası çözümleme içindir: geriye dolan kare, çapa bulunduğu ana kadar gecikir.
    Kareler bellekte JPEG tutulur; kesme, tekrar ve ana kamera dışı kare tamponu boşaltır.
    Kapıyı kısa süre kaçıran kareler, takip kapıdan yeniden geçerse akış duruşuyla köprülenir.
    """

    def __init__(self, fps: float = 15.0, *, filters: bool = True) -> None:
        self._forward = BroadcastTracker(fps, filters=filters)
        self._buffer: deque[tuple[int, np.ndarray]] = deque(maxlen=BACKFILL_FRAMES)
        self._gap: list[tuple[int, np.ndarray]] = []

    def feed(self, k: int, bgr: np.ndarray) -> list[tuple[int, TrackFrame]]:
        """(kare no, sonuç) listesi: bu kare ve varsa geriye dolan kareler."""
        import cv2

        result = self._forward.step(bgr)
        out = [(k, result)]
        if result.state == "gate" and result.carried is not None:
            self._gap.append((k, result.carried))
        else:
            if result.state == "tracked":
                out += [(gap_k, TrackFrame(pose, "bridged", origin=result.origin)) for gap_k, pose in self._gap]
            self._gap = []
        if result.state in {"anchored", "relocalized"} and result.homography is not None:
            out += self._walk_back(result.homography, bgr, result.origin)
        if result.state == "cut" or result.state not in BUFFERED_STATES:
            self._buffer.clear()
        if result.state in BUFFERED_STATES:
            ok, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, BUFFER_JPEG_QUALITY])
            if ok:
                self._buffer.append((k, encoded))
        return out

    def _walk_back(self, anchor_pose: np.ndarray, anchor_bgr: np.ndarray, origin: str) -> list[tuple[int, TrackFrame]]:
        import cv2

        filled: list[tuple[int, TrackFrame]] = []
        h, coast = anchor_pose, 0
        next_gray = cv2.cvtColor(anchor_bgr, cv2.COLOR_BGR2GRAY)
        next_hist = gray_hist(next_gray)
        for k, encoded in reversed(self._buffer):
            bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            hist = gray_hist(gray)
            motion, inliers, _ = flow_step(next_gray, gray)
            corr = float(cv2.compareHist(next_hist, hist, cv2.HISTCMP_CORREL))
            if motion is None or is_cut(inliers, corr):
                break
            carried = h @ np.linalg.inv(motion)
            fit = corrected_pose(carried, daylight_line_mask(bgr))
            if fit is not None:
                h, coast = fit[0], 0
                filled.append((k, TrackFrame(fit[0], "backfilled", fit[1], origin=origin)))
            else:
                h, coast = carried, coast + 1
                if coast > MAX_COAST_FRAMES:
                    break
            next_gray, next_hist = gray, hist
        return filled
