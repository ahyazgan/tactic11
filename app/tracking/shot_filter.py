"""Yayın karesi ana geniş kameradan mı? Kalibrasyondan önce gelen hafif süzgeç (venv-cv).

Kare başına kalibratör yakın çekimde de yüksek inlier alıp yanlış kabul verebiliyor:
az sayıda model noktası her çizgiye oturur (ölçüm:
docs/measurements/line-extraction-daylight-2026-11-02.json). Bu süzgeç o kareleri
kalibratöre girmeden ayırır. Dondurulmuş takip koduna bağlı değildir.

Ana kamerada saha karenin çoğunu kaplar, sahanın üst sınırı karenin üstündedir ve saha
içindeki en büyük nesne küçüktür. Yakın çekim, alçak açı, tribün ve geçiş efekti bu
üçünden en az birini bozar. Tekrarlar ana kameraya benzer açıdan gelirse yakalanamaz.

Eşikler ve sınav: docs/measurements/shot-exam-plan.json, scripts/shot_exam.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WORK_WIDTH = 480
GRASS_HSV_LOW = (28, 25, 18)   # gölgedeki çim için pitch_lines'tan daha gevşek değer ve doygunluk
GRASS_HSV_HIGH = (95, 255, 255)
OPEN_PX = 3                    # bu kalınlıktaki saha çizgileri nesne sayılmaz
ROW_GRASS_MIN = 0.5            # bir satırın saha sayılması için gereken çim oranı

# İlk tahmin, HENÜZ DONDURULMADI. Kör kontrol bu eşiklerle koşulmamalı.
MIN_GRASS_RATIO = 0.5
MAX_FIELD_TOP = 0.42
MAX_OBJECT_HEIGHT = 0.20
MAX_OBJECT_AREA = 0.012


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
