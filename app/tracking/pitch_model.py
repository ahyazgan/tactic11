"""Standart saha çizgi modeli (metre) — kare başına kalibrasyonun referansı.

Hareketli kamerada (yayın) sabit homografi geçersizdir; her karede homografiyi
yeniden bulmak gerekir. Bunun için görüntüdeki beyaz çizgileri saha modelinin
çizgileriyle eşleştiririz. Bu modül o modeli verir: saha çizgileri metre
cinsinden, üzerlerinde örneklenmiş noktalarla.

Koordinat sistemi `calibration.py` ile aynı: orijin sol-üst köşe, x boyuna
0..105 (uzunluk), y enine 0..68 (genişlik).

Neden nokta örneklemesi: homografi kalitesini ölçerken "modelin çizgileri
görüntüdeki çizgi piksellerine ne kadar oturuyor" diye bakarız. Çizgiyi
noktalara bölüp her noktanın en yakın çizgi pikseline uzaklığına bakmak,
çizgi-çizgi eşleştirmeden çok daha basit ve kısmi görünürlüğe dayanıklıdır
(yayında sahanın üçte biri görünür — modelin çoğu noktası kadraj dışındadır
ve doğal olarak elenir).
"""

from __future__ import annotations

import numpy as np

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

_PENALTY_DEPTH = 16.5
_PENALTY_HALF_WIDTH = 20.16      # ceza sahası yarı genişliği (40.32 / 2)
_GOAL_AREA_DEPTH = 5.5
_GOAL_AREA_HALF_WIDTH = 9.16
_CENTRE_RADIUS = 9.15


def pitch_segments() -> list[tuple[float, float, float, float]]:
    """Saha çizgileri: (x1, y1, x2, y2) metre. Orta yuvarlak poligon olarak eklenir."""
    L, W = PITCH_LENGTH_M, PITCH_WIDTH_M
    cy = W / 2.0
    segs: list[tuple[float, float, float, float]] = [
        (0.0, 0.0, L, 0.0),          # üst taç
        (0.0, W, L, W),              # alt taç
        (0.0, 0.0, 0.0, W),          # sol kale çizgisi
        (L, 0.0, L, W),              # sağ kale çizgisi
        (L / 2, 0.0, L / 2, W),      # orta saha çizgisi
    ]
    for side in (0.0, L):
        sign = 1.0 if side == 0.0 else -1.0
        for depth, half in ((_PENALTY_DEPTH, _PENALTY_HALF_WIDTH),
                            (_GOAL_AREA_DEPTH, _GOAL_AREA_HALF_WIDTH)):
            x_out = side + sign * depth
            y_top, y_bot = cy - half, cy + half
            segs += [
                (side, y_top, x_out, y_top),     # üst kenar
                (side, y_bot, x_out, y_bot),     # alt kenar
                (x_out, y_top, x_out, y_bot),    # dikey kenar
            ]
    # Orta yuvarlak — çokgen yaklaşımı
    pts = [
        (L / 2 + _CENTRE_RADIUS * np.cos(t), cy + _CENTRE_RADIUS * np.sin(t))
        for t in np.linspace(0, 2 * np.pi, 33)
    ]
    segs += [
        (float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        for a, b in zip(pts, pts[1:], strict=False)
    ]
    return segs


def model_points(step_m: float = 1.0) -> np.ndarray:
    """Çizgiler üzerinde `step_m` aralıkla örneklenmiş noktalar → (N, 2) metre."""
    out: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in pitch_segments():
        length = float(np.hypot(x2 - x1, y2 - y1))
        n = max(2, int(length / max(step_m, 0.05)) + 1)
        for t in np.linspace(0.0, 1.0, n):
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    return np.asarray(out, dtype=float)


def pitch_corners() -> np.ndarray:
    """Sahanın dört köşesi (metre) — homografi çapası olarak kullanılır."""
    return np.array(
        [[0.0, 0.0], [PITCH_LENGTH_M, 0.0],
         [PITCH_LENGTH_M, PITCH_WIDTH_M], [0.0, PITCH_WIDTH_M]],
        dtype=float,
    )
