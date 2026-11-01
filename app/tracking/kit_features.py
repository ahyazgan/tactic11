"""Takip başına forma rengi kaydı — dondurulmuş takip hattına dokunmadan.

`app.tracking.teams` (dondurulmuş) her takibin gövde bölgesindeki en parlak %40
pikselin ortalamasıyla takım atar. Güneşli sahada uzak/küçük oyuncunun en parlak
pikselleri beyaz şerit ve pusla doluyor: mavi forma da sarı forma da "beyaza
yakın" çıkıyor ve aynı takıma düşüyor (docs/TAKIM-AYRIMI-GUNES.md). Bu modül
aynı kutulardan iki özellik daha toplar ki sonradan parlaklıktan bağımsız bir
atama yapılabilsin:

- `bright`: üretim özelliğinin kendisi (`teams.torso_color`), karşılaştırma için
- `median`: gövde bölgesinde çim dışı piksellerin ortanca RGB'si (beyaz
  şeritten çok kumaşı temsil eder)

`KitRecorder` örnekleme karelerinde (`observation_hook`) biriktirir ve segment
sonunda takip başına ortancaları yazar; GPU işi yoktur.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from app.tracking.teams import torso_color


def torso_median_color(frame_rgb: np.ndarray, xyxy: tuple[float, float, float, float]) -> np.ndarray | None:
    """Gövde bölgesinde (yükseklik %10–55, genişlik %20–80) çim dışı piksellerin ortanca RGB'si."""
    x1, y1, x2, y2 = (round(v) for v in xyxy)
    h, w = frame_rgb.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 - x1 < 2 or y2 - y1 < 4:
        return None
    bw, bh = x2 - x1, y2 - y1
    crop = frame_rgb[y1 + int(bh * 0.10):y1 + int(bh * 0.55), x1 + int(bw * 0.20):x1 + int(bw * 0.80)]
    crop = crop.reshape(-1, 3).astype(float)
    if crop.size == 0:
        return None
    r, g, b = crop[:, 0], crop[:, 1], crop[:, 2]
    kept = crop[~((g > r * 1.12) & (g > b * 1.12))]
    if len(kept) < max(4, len(crop) * 0.12):
        kept = crop
    return np.median(kept, axis=0)


class KitRecorder:
    """Örnek başına takip kutularından forma özelliklerini biriktirir."""

    def __init__(self) -> None:
        self._bright: dict[int, list[np.ndarray]] = defaultdict(list)
        self._median: dict[int, list[np.ndarray]] = defaultdict(list)
        self._heights: dict[int, list[float]] = defaultdict(list)

    def observe(self, rgb: np.ndarray, persons: list[tuple[int, float, float, float, float, float]]) -> None:
        for tid, x1, y1, x2, y2, _conf in persons:
            box = (x1, y1, x2, y2)
            bright = torso_color(rgb, box)
            median = torso_median_color(rgb, box)
            if bright is None or median is None:
                continue
            self._bright[int(tid)].append(bright)
            self._median[int(tid)].append(median)
            self._heights[int(tid)].append(float(y2 - y1))

    def summary(self) -> dict[str, dict[str, Any]]:
        """Takip (yerel kimlik) → {bright, median, height_px, n}; JSON'a hazır."""
        out: dict[str, dict[str, Any]] = {}
        for tid, obs in self._bright.items():
            out[str(tid)] = {
                "bright": [round(float(v), 1) for v in np.median(np.vstack(obs), axis=0)],
                "median": [round(float(v), 1) for v in np.median(np.vstack(self._median[tid]), axis=0)],
                "height_px": round(float(np.median(self._heights[tid])), 1),
                "n": len(obs),
            }
        return out
