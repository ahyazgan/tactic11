"""Yayın karesi ana geniş kameradan mı? Kalibrasyondan önce gelen hafif süzgeç (venv-cv).

Kare başına kalibratör yakın çekimde de yüksek inlier alıp yanlış kabul verebiliyor:
az sayıda model noktası her çizgiye oturur (ölçüm:
docs/measurements/line-extraction-daylight-2026-11-02.json). Bu süzgeç o kareleri
kalibratöre girmeden ayırır. Dondurulmuş takip koduna bağlı değildir.

İki katman:

1. `classify_shot`, tek kareye bakar. Ana kamerada saha karenin çoğunu kaplar, sahanın
   üst sınırı karenin üstündedir ve saha içindeki en büyük nesne küçüktür.
2. `ReplayTracker`, zamana bakar. Ana kameraya benzer açıdan gelen tekrar tek kareden
   ayrılamaz, ama J.League yayınında tekrar kırmızı logo geçişiyle başlar ve biter.
   Bu işaret yayıncıya özgüdür; geçiş görülmeyen yayında yalnız 1. katman çalışır.

Eşikler 3 geliştirme maçıyla seçildi ve kör kontrolden önce donduruldu:
docs/measurements/shot-exam-plan.json. Kontrol sonucuna bakıp değiştirilmez.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

WORK_WIDTH = 480
GRASS_HSV_LOW = (28, 25, 18)   # gölgedeki çim için pitch_lines'tan daha gevşek değer ve doygunluk
GRASS_HSV_HIGH = (95, 255, 255)
OPEN_PX = 3                    # bu kalınlıktaki saha çizgileri nesne sayılmaz
ROW_GRASS_MIN = 0.5            # bir satırın saha sayılması için gereken çim oranı

MIN_GRASS_RATIO = 0.7
MAX_FIELD_TOP = 0.3
MAX_OBJECT_HEIGHT = 0.2
MAX_OBJECT_AREA = 0.02

WIPE_SAMPLE_FPS = 5.0          # ReplayTracker bu sıklıkta beslenmeli; geçiş 1 saniyeden kısa
WIPE_RED_RATIO = 0.08          # geçiş sayılan doymuş kırmızı oranı
WIPE_MIN_PEAK = 0.15           # ölçülen tepeler 0,23–0,34
WIPE_MAX_S = 1.2               # ölçülen süreler 0,6–0,8 sn; daha uzun kırmızı forma veya tribündür
MAX_REPLAY_S = 60.0            # ölçülen en uzun 39 sn; kaçan geçiş ana kamerayı sonsuza dek elemesin


@dataclass(frozen=True)
class ShotFeatures:
    grass_ratio: float      # karenin çim oranı
    field_top: float        # sahanın başladığı satır / kare yüksekliği
    object_height: float    # saha içindeki en uzun nesne / kare yüksekliği
    object_area: float      # saha içindeki en büyük nesne / kare alanı


@dataclass(frozen=True)
class ShotVerdict:
    is_main: bool
    reason: str
    features: ShotFeatures


def shot_features(bgr: np.ndarray) -> ShotFeatures:
    import cv2

    h, w = bgr.shape[:2]
    work_h = max(1, round(h * WORK_WIDTH / w))
    small = cv2.resize(bgr, (WORK_WIDTH, work_h), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH)) > 0
    rows = grass.mean(axis=1)
    field_rows = np.flatnonzero(rows >= ROW_GRASS_MIN)
    if field_rows.size == 0:
        return ShotFeatures(float(grass.mean()), 1.0, 0.0, 0.0)
    top = int(field_rows[0])

    objects = (~grass).astype(np.uint8)
    objects[:top] = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (OPEN_PX, OPEN_PX))
    objects = cv2.morphologyEx(objects, cv2.MORPH_OPEN, kernel)
    count, _labels, stats, _ = cv2.connectedComponentsWithStats(objects, connectivity=8)
    height, area = 0, 0
    for i in range(1, count):
        # Üst sınıra yapışık parça tribündür, sahadaki nesne değil.
        if stats[i, cv2.CC_STAT_TOP] <= top:
            continue
        height = max(height, int(stats[i, cv2.CC_STAT_HEIGHT]))
        area = max(area, int(stats[i, cv2.CC_STAT_AREA]))
    return ShotFeatures(float(grass.mean()), top / work_h, height / work_h, area / (work_h * WORK_WIDTH))


def classify_shot(bgr: np.ndarray) -> ShotVerdict:
    f = shot_features(bgr)
    if f.grass_ratio < MIN_GRASS_RATIO:
        return ShotVerdict(False, "çim az", f)
    if f.field_top > MAX_FIELD_TOP:
        return ShotVerdict(False, "saha sınırı alçak", f)
    if f.object_height > MAX_OBJECT_HEIGHT:
        return ShotVerdict(False, "nesne uzun", f)
    if f.object_area > MAX_OBJECT_AREA:
        return ShotVerdict(False, "nesne büyük", f)
    return ShotVerdict(True, "ana kamera", f)


def red_ratio(bgr: np.ndarray) -> float:
    """Karedeki doymuş logo kırmızısının oranı."""
    import cv2

    small = cv2.resize(bgr, (240, 135), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return float((((hue <= 4) | (hue >= 176)) & (sat >= 200) & (val >= 170)).mean())


class ReplayTracker:
    """Kırmızı logo geçişlerinden "şu an tekrar mı?" durumunu tutar.

    Kısa ve parlak her kırmızı dilim durumu çevirir: tekrar geçişle başlar, geçişle biter.
    Uzun kırmızı dilim (forma, tribün) geçiş sayılmaz. Kaçan bitiş geçişinde durum
    `MAX_REPLAY_S` sonra kendiliğinden kapanır. Geçişin kendi kareleri tekrar sayılır.
    """

    def __init__(self) -> None:
        self._in_replay = False
        self._replay_start = 0.0
        self._run_start: float | None = None
        self._run_last = 0.0
        self._run_peak = 0.0

    def update(self, t_s: float, ratio: float) -> bool:
        """Zaman sırasıyla çağrılır; bu an tekrar içindeyse True döner."""
        if ratio >= WIPE_RED_RATIO:
            if self._run_start is None:
                self._run_start, self._run_peak = t_s, 0.0
            self._run_last = t_s
            self._run_peak = max(self._run_peak, ratio)
            return True
        if self._run_start is not None:
            is_wipe = self._run_last - self._run_start <= WIPE_MAX_S and self._run_peak >= WIPE_MIN_PEAK
            if is_wipe:
                self._in_replay = not self._in_replay
                self._replay_start = self._run_start
            self._run_start = None
        if self._in_replay and t_s - self._replay_start > MAX_REPLAY_S:
            self._in_replay = False
        return self._in_replay
