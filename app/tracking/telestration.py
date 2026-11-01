"""Otomatik telestrasyon — takip çıktısından yayın grafiği gibi çizim.

Analistin elle çizdiği halka/çizgi/etiketi sistem kendisi üretir. Girdi takip
hattının çıktısıdır (`TrackingFrame`, saha koordinatı) + kalibrasyon; her öğe
SAHA uzayında hesaplanıp görüntüye geri izdüşürülür. Böylece dondurulmuş takip
hattına dokunmadan hem kayıtlı videoda hem canlı segmentlerde çalışır.

- **Halka** — oyuncunun ayak noktasında 0,9 m yarıçaplı saha çemberinin
  izdüşümü (sahaya yatık elips), takım renginde.
- **Blok çizgileri** — topa sahip OLMAYAN takımın savunma hattı ve önündeki hat,
  hattaki oyuncuların genişliğinde sahaya yapışık çizgi; aradaki şerit ve mesafe.
- **Pres vurgusu** — topa 5 m içindeki savunan oyuncuların halkası vurgulanır.
- **Faz etiketi** — "Orta blok · pres" gibi; savunma hattının kendi kalesine
  uzaklığından ve top çevresindeki baskıdan.

İzdüşüm: homografide kapalı biçimde ters; TPS'de ileri modelin sayısal tersi,
yalnız destek bölgesinde (bkz. `_Projector`).

Kapılar (yanlış çizim, hiç çizim olmamasından kötüdür): kalibrasyon bağımsız
doğrulanmamışsa (`calibration_validation`: çizgi doğrulaması ya da saha
işareti noktalı kalibrasyonun LOO'su) veya hatası eşik üstündeyse, sahiplik
bilinmiyorsa, hücum yönü belirsizse ya da savunan takımdan yeterli oyuncu
görünmüyorsa çizgi ve etiket üretilmez; nedeni `Telestrator.gate_counts` sayar.
Halkalar yine çizilir.

Sınır: blok eşikleri (30 / 45 m) yaygın antrenörlük kullanımından alınmış
sezgisel değerlerdir, etiketli maçla ayarlanmadı. Konumlar ayak/top zemin
izdüşümüdür; havadaki topta pres sayımı yanılabilir. Gerçek görüntüde kaleciler
çoğu zaman görünmediği için hücum yönünü operatörün vermesi asıl yoldur.
"""

from __future__ import annotations

import os
from collections import Counter, deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np

from app.domain import TrackingFrame
from app.engine.space_map.compute import (
    LINE_CLUSTER_GAP_M,
    MIN_LINE_PLAYERS,
    infer_attack_direction,
)
from app.engine.tracking.compute import PRESS_RADIUS_M
from app.tracking.calibration import PitchCalibration, tps_apply
from app.tracking.person_filter import (
    BOUNDARY_TOLERANCE_HEIGHT,
    annotated_boundary,
    inside_boundary,
)
from app.tracking.pitch_model import PITCH_LENGTH_M, PITCH_WIDTH_M, pitch_segments

LOW_BLOCK_MAX_M = 30.0       # savunma hattı kendi kalesine < 30 m → alçak blok
MID_BLOCK_MAX_M = 45.0       # 30–45 m → orta blok; üstü yüksek blok
PRESS_NEAREST_MAX_M = 3.0    # pres: en yakın savunan ≤ 3 m ...
PRESS_MIN_PLAYERS = 2        # ... ve 5 m içinde en az 2 savunan
POSSESSION_MAX_M = 4.0       # topa bu mesafeden uzak en yakın oyuncu sahiplik oyu vermez
RING_RADIUS_M = 0.9
MIN_TEAM_PLAYERS = 6         # çizgi/etiket için savunan takımdan görünür oyuncu
# Kalibrasyon kapısı. Hata, kalibrasyonun kendi uydurma noktalarında değil BAĞIMSIZ
# doğrulamada ölçülmeli: oyuncu konumlarından türetilmiş bir kalibrasyon kendi
# noktalarında 0,76 m LOO verip saha çizgilerinde 10,7 m sapabilir
# (docs/TESPIT-KALITESI-DENETIMI.md). Bu yüzden kabul edilen kaynaklar:
# meta'daki çizgi doğrulaması, ya da noktaları saha işaretleri üzerinde olan
# kalibrasyonun LOO'su (o zaman her bırakılan nokta bağımsız bir saha işaretidir).
# 2,0 m: 15 m'lik blok bantlarının ve ölçülen ~4–6 m'lik hat hatasının çok altında.
# (1,5 m'den, çizgi kalibrasyonunun 1,76 m LOO'su görüldükten sonra yükseltildi.)
MAX_REPROJECTION_M = 2.0
LANDMARK_TOLERANCE_M = 0.5   # nokta bir saha işaretine bu kadar yakınsa işaret üzerindedir
LANDMARK_SHARE = 0.8         # noktaların bu payı işaret üzerindeyse kalibrasyon işaret tabanlıdır
LINE_CHECK_NEAR_PX = 18.0    # çizgi doğrulaması: model noktası en çok bu kadar uzaktaki çizgiyle eşleşir
LINE_CHECK_MIN_COVERAGE = 0.5  # görünür model noktalarının en az bu payı bir çizgiyle eşleşmeli
LINE_CHECK_MIN_POINTS = 30
DIRECTION_WINDOW_S = 10.0
POSSESSION_WINDOW_S = 1.0
LABEL_HOLD_S = 1.0           # etiket ancak bu süre kararlıysa değişir
TPS_INVERSE_ITERATIONS = 8
LINE_SMOOTHING = 0.35        # hat derinliği/aralığı için üstel yumuşatma: her 0,2 sn'de yeni değerin payı
LINE_SMOOTHING_PERIOD_S = 0.2
INTERPOLATE_MAX_GAP_S = 0.6  # takip kareleri arası bundan uzunsa enterpolasyon yok (kopma)
LINE_MARGIN_M = 3.0          # çizgi hattın uç oyuncularından bu kadar taşar
TPS_INVERSE_MAX_RESIDUAL_M = 0.1  # sayısal ters, ileri dönüşümle bu kadar tutmalı

_FONT_PATH = Path(__file__).resolve().parents[2] / "frontend/public/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2"


@dataclass(frozen=True)
class Mark:
    """Tek çizim öğesi (görüntü pikseli). JSON'a `dataclasses.asdict` ile çevrilir."""

    kind: str                                  # ring | line | band | label | ball
    points: tuple[tuple[float, float], ...]
    team: int | None = None
    emphasis: bool = False
    text: str | None = None


@dataclass(frozen=True)
class PlayerSpot:
    """Bir oyuncunun saha konumu (m); `team` 0 = ev sahibi, 1 = deplasman, None = atanmamış."""

    tid: int
    team: int | None
    x_m: float
    y_m: float


def interpolate_spots(a: list[PlayerSpot], b: list[PlayerSpot], w: float) -> list[PlayerSpot]:
    """İki takip karesi arasında `w` ∈ [0, 1] konumu. İkisinde de olan kimlik doğrusal
    enterpole edilir (takımı `a`'dan); yalnız birinde olan, yakın olduğu karede gösterilir."""
    later = {p.tid: p for p in b}
    out = []
    for p in a:
        q = later.pop(p.tid, None)
        if q is not None:
            out.append(PlayerSpot(p.tid, p.team, p.x_m + w * (q.x_m - p.x_m), p.y_m + w * (q.y_m - p.y_m)))
        elif w < 0.5:
            out.append(p)
    if w >= 0.5:
        out.extend(later.values())
    return out


def interpolate_point(a: tuple[float, float] | None, b: tuple[float, float] | None,
                      w: float) -> tuple[float, float] | None:
    if a is None or b is None:
        return a if w < 0.5 else b
    return a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1])


def spots_from_frame(frame: TrackingFrame, home_team_id: int, away_team_id: int, calib: PitchCalibration,
                     ) -> tuple[list[PlayerSpot], tuple[float, float] | None, int | None]:
    """TrackingFrame → (oyuncular, top m, sahip takım 0/1/None)."""
    index = {home_team_id: 0, away_team_id: 1}
    L, W = calib.pitch_length_m, calib.pitch_width_m
    players = [PlayerSpot(p.player_external_id,
                          index.get(p.team_external_id) if p.team_external_id is not None else None,
                          p.x / 100.0 * L, p.y / 100.0 * W) for p in frame.players]
    ball = (frame.ball.x / 100.0 * L, frame.ball.y / 100.0 * W) if frame.ball is not None else None
    owner = frame.possession_team_external_id
    return players, ball, index.get(owner) if owner is not None else None


def _convex_hull(points: np.ndarray) -> np.ndarray | None:
    """Monoton zincir; en az üç doğrusal olmayan nokta yoksa None."""
    pts = sorted(set(map(tuple, np.asarray(points, dtype=float).tolist())))
    if len(pts) < 3:
        return None

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    hull = half(pts) + half(pts[::-1])
    return np.asarray(hull) if len(hull) >= 3 else None


def _support_polygon(calib: PitchCalibration) -> np.ndarray | None:
    boundary = annotated_boundary(calib)
    if boundary is not None:
        return boundary
    return _convex_hull(np.array([p.image for p in calib.points]))


def _on_marking(points: np.ndarray, tolerance: float = LANDMARK_TOLERANCE_M) -> np.ndarray:
    """Saha noktaları (N×2 m) standart bir saha işaretinin (çizgi, ceza/kale sahası,
    orta yuvarlak, penaltı ve orta noktası) üzerinde mi."""
    segs = np.array(pitch_segments(), dtype=float)
    a, b = segs[:, :2], segs[:, 2:]
    edge = b - a
    delta = points[:, None, :] - a[None]
    t = np.clip(np.sum(delta * edge, axis=2) / np.maximum(np.sum(edge * edge, axis=1), 1e-12), 0.0, 1.0)
    to_line = np.linalg.norm(delta - t[:, :, None] * edge[None], axis=2).min(axis=1)
    spots = np.array([[11.0, PITCH_WIDTH_M / 2], [PITCH_LENGTH_M - 11.0, PITCH_WIDTH_M / 2],
                      [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2]])
    to_spot = np.linalg.norm(points[:, None, :] - spots[None], axis=2).min(axis=1)
    return np.minimum(to_line, to_spot) <= tolerance


def _line_groups(step_m: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Saha modeli noktaları ve yön grubu: 0 = sabit x (kale/orta/ceza dikeyleri),
    1 = sabit y (taç, ceza/kale yatayları), 2 = eğri (orta yuvarlak)."""
    pts: list[tuple[float, float]] = []
    groups: list[int] = []
    for x1, y1, x2, y2 in pitch_segments():
        group = 0 if abs(x2 - x1) < 1e-6 else 1 if abs(y2 - y1) < 1e-6 else 2
        n = max(2, int(float(np.hypot(x2 - x1, y2 - y1)) / step_m) + 1)
        for t in np.linspace(0.0, 1.0, n):
            pts.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
            groups.append(group)
    return np.asarray(pts, dtype=float), np.asarray(groups)


def line_validation_error(h_img_to_pitch: np.ndarray, dist_map: np.ndarray) -> tuple[float | None, float]:
    """Homografiyi görüntüdeki beyaz saha çizgilerine karşı doğrula → (hata m | None, kapsama).

    Saha modelinin çizgi noktaları (1 m aralık) görüntüye izdüşürülür; görüntü
    içindekilerin en yakın çizgi pikseline uzaklığı (`dist_map`, px) o noktadaki
    yerel ölçekle (piksel başına metre, homografi Jacobian'ının geometrik ortalaması)
    metreye çevrilir; ≤ `LINE_CHECK_NEAR_PX` uzaklıktakiler eşleşmiş sayılır.
    Noktalar yönlerine göre gruplanır (sabit-x çizgiler, sabit-y çizgiler, eğri):
    tek bir medyan, çizgi yönündeki kaymayı göremez (x'te 3 m kayan oturmada yatay
    çizgiler yine üst üste düşer). Hata, ≥10 görünür noktası olan grupların
    eşleşmiş medyanlarının en büyüğüdür; böyle bir grupta eşleşme yarının altındaysa
    (çizgi örtülü ya da yanlış oturma) None döner ve kalibrasyon doğrulanmamış kalır.
    Kapsama tüm görünür noktaların eşleşen payıdır. Oturtma da bu çizgilere
    yapıldığından değer örneklem içidir: uyum kalitesini ölçer, bağımsız saha
    doğruluğunu değil (yine de oyuncudan türetilmiş LOO gibi çizgilerden kopuk değildir)."""
    h, w = dist_map.shape[:2]
    pts, groups = _line_groups()
    inv = np.linalg.inv(h_img_to_pitch)
    q = np.c_[pts, np.ones(len(pts))] @ inv.T
    ok = q[:, 2] > 1e-9
    uv = q[:, :2] / np.where(ok, q[:, 2], 1.0)[:, None]
    ok &= (uv[:, 0] >= 0) & (uv[:, 0] < w - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < h - 1)
    if int(ok.sum()) < LINE_CHECK_MIN_POINTS:
        return None, 0.0
    uv, groups = uv[ok], groups[ok]
    d_px = dist_map[uv[:, 1].astype(int), uv[:, 0].astype(int)].astype(float)
    near = d_px <= LINE_CHECK_NEAR_PX
    coverage = float(near.mean())

    def to_pitch(p: np.ndarray) -> np.ndarray:
        r = np.c_[p, np.ones(len(p))] @ h_img_to_pitch.T
        return r[:, :2] / r[:, 2:3]

    base = to_pitch(uv)
    dx = to_pitch(uv + [1.0, 0.0]) - base
    dy = to_pitch(uv + [0.0, 1.0]) - base
    error_m = d_px * np.sqrt(np.abs(dx[:, 0] * dy[:, 1] - dx[:, 1] * dy[:, 0]))
    worst: float | None = None
    for g in (0, 1, 2):
        member = groups == g
        if int(member.sum()) < 10:
            continue
        if float(near[member].mean()) < LINE_CHECK_MIN_COVERAGE:
            return None, coverage
        group_error = float(np.median(error_m[member & near]))
        worst = group_error if worst is None else max(worst, group_error)
    return worst, coverage


def calibration_validation(calib: PitchCalibration) -> tuple[str, float | None]:
    """Kapının kullanacağı bağımsız hata: (kaynak, metre).

    - `line_validation`: `meta["line_validation_error_m"]` (saha çizgisi noktalarında ölçülmüş)
    - `landmark_loo`: noktaların ≥%80'i saha işareti üzerinde → LOO hatası
    - `unverified`: ikisi de yok (oyuncudan türetilmiş, yapay ızgara, standart dışı ölçü)
    """
    meta = calib.meta if isinstance(calib.meta, dict) else {}
    value = meta.get("line_validation_error_m")
    if isinstance(value, (int, float)) and np.isfinite(value):
        return "line_validation", float(value)
    standard = (abs(calib.pitch_length_m - PITCH_LENGTH_M) < 1e-6
                and abs(calib.pitch_width_m - PITCH_WIDTH_M) < 1e-6)
    pts = np.array([p.pitch for p in calib.points], dtype=float)
    if standard and len(pts) and float(_on_marking(pts).mean()) >= LANDMARK_SHARE:
        return "landmark_loo", calib.reprojection_error_m
    return "unverified", None


class _Projector:
    """Saha metresi → görüntü pikseli.

    Homografi: kapalı biçimde ters; ufkun arkasına düşen nokta reddedilir.
    TPS: ters spline yok; ileri modelin sayısal tersi alınır (homografi
    tersinden başlayan Gauss-Newton). İleri dönüşümle geri doğrulanmayan ya da
    destek bölgesi dışına düşen nokta reddedilir — TPS orada ekstrapole eder
    (docs/TOP-SINIR-UYUSMAZLIGI-TANI.md). Destek bölgesi: işaretli saha sınırı,
    yoksa kontrol noktalarının görüntüdeki dışbükey zarfı (enterpolasyon alanı).
    """

    def __init__(self, calib: PitchCalibration) -> None:
        self.calib = calib
        self.inv = np.linalg.inv(calib.homography)
        ref = calib.points[0].pitch
        self.sign = np.sign((self.inv @ np.array([ref[0], ref[1], 1.0]))[2])
        w, h = calib.image_size
        self.limit = 4.0 * max(w, h)
        self.boundary = _support_polygon(calib) if calib.method == "tps" else None
        self.tolerance_px = BOUNDARY_TOLERANCE_HEIGHT * h
        self.usable = calib.method == "homography" or self.boundary is not None
        self._validation: tuple[str, float | None] | None = None

    @property
    def validation(self) -> tuple[str, float | None]:
        if self._validation is None:
            self._validation = calibration_validation(self.calib)
        return self._validation

    def forward(self, q: np.ndarray) -> np.ndarray:
        """Vektörel `image_to_pitch_m` (N×2 piksel → N×2 m). calibration.py ölçülmüş
        kontrol kodunun parçası olduğu için (tests/test_guarded_control.py) yöntem
        oraya eklenmez; aynı hesap homografi + artık TPS modeliyle burada yapılır."""
        q = np.atleast_2d(np.asarray(q, dtype=float))
        h = np.c_[q, np.ones(len(q))] @ self.calib.homography.T
        base = h[:, :2] / h[:, 2:3]
        return base + tps_apply(self.calib._tps, q) if self.calib.method == "tps" else base

    def inside(self, uv: np.ndarray) -> np.ndarray:
        """Görüntü noktası işaretli saha sınırı içinde mi (sınır yoksa hep evet)."""
        if self.boundary is None:
            return np.ones(len(uv), dtype=bool)
        return inside_boundary(uv, self.boundary, self.tolerance_px)

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(N×2 piksel, N geçerlilik maskesi)."""
        q = np.c_[pts, np.ones(len(pts))] @ self.inv.T
        ok = (np.sign(q[:, 2]) == self.sign) & (np.abs(q[:, 2]) > 1e-9)
        out = q[:, :2] / np.where(ok, q[:, 2], 1.0)[:, None]
        if not self.usable:
            return out, np.zeros(len(pts), dtype=bool)
        if self.calib.method == "tps":
            out, converged = self._refine(out, pts)
            ok &= converged
        ok &= np.all(np.abs(out) < self.limit, axis=1)
        ok &= self.inside(out)
        return out, ok

    def _refine(self, guess: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        forward = self.forward
        u, step = guess.copy(), 0.5
        for _ in range(TPS_INVERSE_ITERATIONS):
            base = forward(u)
            f = base - target
            if np.max(np.abs(f)) < 1e-3:
                break
            dx = (forward(u + [step, 0.0]) - base) / step
            dy = (forward(u + [0.0, step]) - base) / step
            det = dx[:, 0] * dy[:, 1] - dy[:, 0] * dx[:, 1]
            safe = np.where(np.abs(det) > 1e-12, det, np.inf)
            # 2×2 Jacobian'ın tersi: [[dy1, -dy0], [-dx1, dx0]] / det
            u = u - np.c_[dy[:, 1] * f[:, 0] - dy[:, 0] * f[:, 1],
                          -dx[:, 1] * f[:, 0] + dx[:, 0] * f[:, 1]] / safe[:, None]
        residual = np.hypot(*(forward(u) - target).T)
        return u, residual <= TPS_INVERSE_MAX_RESIDUAL_M

    def rings(self, centers: np.ndarray, radius: float, n: int = 24) -> tuple[np.ndarray, np.ndarray]:
        """Saha çemberlerinin izdüşümü (K×n×2) ve geçerlilik (K). Merkezler tek seferde
        ters dönüştürülür; çember, merkezde ileri dönüşümün sayısal Jacobian'ının tersiyle
        taşınır (0,9 m'de doğrusal yaklaşım; oyuncu başına ayrı ters dönüşüm gerekmez)."""
        uv, ok = self.project(centers)
        if not len(centers):
            return np.empty((0, n, 2)), ok
        step = 0.5
        base = self.forward(uv)
        dx = (self.forward(uv + [step, 0.0]) - base) / step     # d(saha)/du
        dy = (self.forward(uv + [0.0, step]) - base) / step     # d(saha)/dv
        det = dx[:, 0] * dy[:, 1] - dy[:, 0] * dx[:, 1]
        ok &= np.abs(det) > 1e-12
        safe = np.where(ok, det, 1.0)
        a = np.linspace(0, 2 * np.pi, n, endpoint=False)
        off = radius * np.c_[np.cos(a), np.sin(a)]               # n×2 saha ofseti
        # [du, dv] = J⁻¹ · [dX, dY],  J = [[dx0, dy0], [dx1, dy1]]
        du = (dy[:, None, 1] * off[None, :, 0] - dy[:, None, 0] * off[None, :, 1]) / safe[:, None]
        dv = (-dx[:, None, 1] * off[None, :, 0] + dx[:, None, 0] * off[None, :, 1]) / safe[:, None]
        pts = uv[:, None, :] + np.stack([du, dv], axis=2)
        ok &= self.inside(pts.reshape(-1, 2)).reshape(len(centers), n).all(axis=1)
        return pts, ok

    def __call__(self, pts: np.ndarray) -> np.ndarray | None:
        """Hepsi geçerliyse izdüşüm, değilse None (halka, tek nokta)."""
        out, ok = self.project(pts)
        return out if ok.all() else None

    def run(self, pts: np.ndarray) -> np.ndarray | None:
        """Geçerli noktaların en uzun ardışık dizisi (çizgi; ≥2 nokta)."""
        out, ok = self.project(pts)
        best: tuple[int, int] = (0, 0)
        start = None
        for i, good in enumerate([*ok, False]):
            if good and start is None:
                start = i
            elif not good and start is not None:
                if i - start > best[1] - best[0]:
                    best = (start, i)
                start = None
        return out[best[0]:best[1]] if best[1] - best[0] >= 2 else None


@dataclass(frozen=True)
class Line:
    """Bir hat: kendi kalesine ortalama uzaklık (m) ve oyuncuların enine aralığı."""

    depth: float
    y_min: float
    y_max: float


def _lines(players: list[tuple[float, float]], statistic: str = "mean") -> list[Line]:
    """(kendi kalesine uzaklık, y) oyuncularını büyük boşluklardan hatlara böl;
    hat derinliği üyelerin ortalaması ya da medyanı."""
    groups: list[list[tuple[float, float]]] = []
    for d, y in sorted(players):
        if groups and d - groups[-1][-1][0] <= LINE_CLUSTER_GAP_M:
            groups[-1].append((d, y))
        else:
            groups.append([(d, y)])
    if len(groups) > 1 and len(groups[0]) == 1:
        groups = groups[1:]  # izole en derin = kaleci
    center = np.median if statistic == "median" else np.mean
    return [Line(float(center([d for d, _ in g])), min(y for _, y in g), max(y for _, y in g))
            for g in groups if len(g) >= MIN_LINE_PLAYERS]


@dataclass(frozen=True)
class TelestrationConfig:
    """Hat/etiket davranışının ayarları; varsayılanlar ölçülmüş üretim davranışıdır
    (docs/OTOMATIK-TELESTRASYON.md)."""

    line_smoothing: float = LINE_SMOOTHING   # her 0,2 sn'de yeni hat değerinin payı
    label_hold_s: float = LABEL_HOLD_S       # etiket değişmeden önce gereken kararlılık
    min_track_s: float = 0.0                 # hat/pres hesabına girmek için kesintisiz görünme
    line_statistic: str = "mean"             # hat derinliği: mean | median

    def __post_init__(self) -> None:
        if self.line_statistic not in ("mean", "median"):
            raise ValueError("line_statistic mean ya da median olmalı")
        if not 0.0 < self.line_smoothing <= 1.0 or self.label_hold_s < 0 or self.min_track_s < 0:
            raise ValueError("geçersiz telestrasyon ayarı")


def block_label(def_line_m: float, pressing: bool) -> str:
    if def_line_m < LOW_BLOCK_MAX_M:
        base = "Alçak blok"
    elif def_line_m < MID_BLOCK_MAX_M:
        base = "Orta blok"
    else:
        base = "Yüksek blok"
    return f"{base} · pres" if pressing else base


class Telestrator:
    """Kare kare çizim üretir; yön, sahiplik ve etiket için kısa geçmiş tutar."""

    def __init__(self, fps: float, home_attack_direction: int = 0,
                 config: TelestrationConfig | None = None) -> None:
        """`home_attack_direction`: takım 0'ın hücum yönü (+1: saha x artan, -1: azalan,
        0: kaleci/en derin oyuncudan çıkar). Devre boyunca sabittir; gerçek görüntüde
        kaleciler çoğu zaman görünmediği için canlıda operatör girdisi asıl yoldur."""
        fps = max(fps, 1.0)
        if home_attack_direction not in (-1, 0, 1):
            raise ValueError("home_attack_direction -1, 0 veya 1 olmalı")
        self._home_attack = home_attack_direction
        self._frames: deque[SimpleNamespace] = deque(maxlen=max(1, round(DIRECTION_WINDOW_S * fps)))
        self._owners: deque[int] = deque(maxlen=max(1, round(POSSESSION_WINDOW_S * fps)))
        self.config = config or TelestrationConfig()
        self._hold = max(1, round(self.config.label_hold_s * fps))
        # kare hızından bağımsız aynı zaman sabiti: 0,2 sn'de line_smoothing kadar
        self._alpha = 1.0 - (1.0 - self.config.line_smoothing) ** (1.0 / (fps * LINE_SMOOTHING_PERIOD_S))
        self._min_track = max(1, round(self.config.min_track_s * fps))
        self._seen: dict[int, int] = {}
        self._candidate: str | None = None
        self._streak = 0
        self.label: str | None = None
        # Kare başına çizgi/etiketin neden çizilmediği (calibration | possession |
        # direction | players | lines) veya "drawn"; iddia tekrarlanabilir olsun diye.
        self.gate_counts: Counter[str] = Counter()
        self._line_state: list[Line] = []
        # Son karenin ölçümleri (değerlendirme ve panel için): çizilmeme nedeni,
        # savunan takım, yumuşatılmış hatlar, presçi sayısı.
        self.last_gate: str | None = None
        self.last_defending: int | None = None
        self.last_lines: list[Line] = []
        self.last_pressers = 0
        self._proj: _Projector | None = None

    def _direction(self, team: int) -> int:
        if self._home_attack:
            return self._home_attack if team == 0 else -self._home_attack
        # Kural space_map ile aynı kalsın diye onun fonksiyonu kullanılır; yalnız
        # players / x / team_external_id / is_keeper alanlarını okur.
        frames = cast("list[TrackingFrame]", list(self._frames))
        direction, _method = infer_attack_direction(frames, team, 1 - team)
        return direction

    def _gate(self, proj: _Projector) -> str | None:
        source, error = proj.validation
        if source == "unverified":
            return "calibration_unverified"
        if error is None or error > MAX_REPROJECTION_M:
            return "calibration"
        return None if self._owners else "possession"

    def _smooth(self, lines: list[Line]) -> list[Line]:
        """Aynı hatlar kareler arasında titremesin; hat değişince (sayı ya da
        hat boşluğundan büyük sıçrama) yumuşatma sıfırlanır."""
        prev, a = self._line_state, self._alpha
        same = len(prev) == len(lines) and all(
            abs(p.depth - n.depth) <= LINE_CLUSTER_GAP_M for p, n in zip(prev, lines, strict=True))
        if same:
            lines = [Line(*(a * nv + (1 - a) * pv for nv, pv in
                            zip((n.depth, n.y_min, n.y_max), (p.depth, p.y_min, p.y_max), strict=True)))
                     for p, n in zip(prev, lines, strict=True)]
        self._line_state = lines
        return lines

    def _settle_label(self, candidate: str | None) -> str | None:
        if candidate == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = candidate, 1
        if self._streak >= self._hold:
            self.label = candidate
        return self.label

    def marks(self, players: list[PlayerSpot], ball_m: tuple[float, float] | None,
              calib: PitchCalibration | None, possession: int | None = None) -> list[Mark]:
        """Bir karenin çizim öğeleri. `possession` verilmezse topa en yakın
        oyuncudan (≤ 4 m) çıkarılır; ikisi de kısa pencerede çoğunluk oyuna girer."""
        out: list[Mark] = []
        proj = self._projector(calib)
        if proj is None or not proj.usable:
            self.gate_counts["calibration"] += 1
            self.last_gate, self.last_defending, self.last_lines, self.last_pressers = "calibration", None, [], 0
            return out
        # yalnız görüntüde destek bölgesine izdüşen oyuncu/top sayılır ve çizilir
        _uv, ok = proj.project(np.array([(p.x_m, p.y_m) for p in players]).reshape(-1, 2))
        players = [p for p, good in zip(players, ok, strict=True) if good]
        ball_px = proj(np.array([ball_m])) if ball_m is not None else None
        if ball_px is None:
            ball_m = None
        pitch = {p.tid: (p.x_m, p.y_m) for p in players if p.team in (0, 1)}
        # kesintisiz görünme sayacı: kısa ömürlü (çoğu hayalet/yanlış) tespitler hat hesabına girmez
        self._seen = {p.tid: self._seen.get(p.tid, 0) + 1 for p in players}
        steady = {tid: xy for tid, xy in pitch.items() if self._seen[tid] >= self._min_track}
        L = proj.calib.pitch_length_m
        self._frames.append(SimpleNamespace(players=[
            SimpleNamespace(x=p.x_m / L * 100.0, team_external_id=p.team, is_keeper=False)
            for p in players if p.team in (0, 1)]))
        if possession is not None and possession in (0, 1):
            self._owners.append(possession)
        elif ball_m is not None and pitch:
            bx, by = ball_m
            dist, owner = min((float(np.hypot(x - bx, y - by)), tid) for tid, (x, y) in pitch.items())
            if dist <= POSSESSION_MAX_M:
                self._owners.append(next(cast(int, p.team) for p in players if p.tid == owner))

        defending: int | None = None
        pressers: set[int] = set()
        candidate: str | None = None
        gate = self._gate(proj)
        if gate is None:
            defending = 1 - Counter(self._owners).most_common(1)[0][0]
            direction = self._direction(defending)
            team_pts = {p.tid: steady[p.tid] for p in players if p.team == defending and p.tid in steady}
            lines = self._smooth(_lines([((xy[0] if direction > 0 else L - xy[0]), xy[1])
                                         for xy in team_pts.values()], self.config.line_statistic))
            if direction == 0:
                gate = "direction"
            elif len(team_pts) < MIN_TEAM_PLAYERS:
                gate = "players"
            elif not lines:
                gate = "lines"
            else:
                if ball_m is not None:
                    near = sorted((float(np.hypot(xy[0] - ball_m[0], xy[1] - ball_m[1])), t)
                                  for t, xy in team_pts.items())
                    close = [t for d, t in near if d <= PRESS_RADIUS_M]
                    if near[0][0] <= PRESS_NEAREST_MAX_M and len(close) >= PRESS_MIN_PLAYERS:
                        pressers = set(close)
                candidate = block_label(lines[0].depth, bool(pressers))
                out += self._block_marks(proj, proj.calib, direction, lines, defending)
        if gate is not None:
            self._line_state = []
        self.gate_counts[gate or "drawn"] += 1
        self.last_gate, self.last_defending = gate or "drawn", defending
        self.last_lines, self.last_pressers = list(self._line_state), len(pressers)
        label = self._settle_label(candidate)

        rings, good = proj.rings(np.array([(p.x_m, p.y_m) for p in players]).reshape(-1, 2), RING_RADIUS_M)
        for p, ring, ok_ring in zip(players, rings, good, strict=True):
            if ok_ring:
                out.append(Mark("ring", tuple(map(tuple, ring.round(1).tolist())), team=p.team,
                                emphasis=p.tid in pressers))
        if ball_px is not None:
            out.append(Mark("ball", (tuple(ball_px[0].round(1).tolist()),)))
        if label:
            out.append(Mark("label", (), team=defending, text=label))
        return out

    def _projector(self, calib: PitchCalibration | None) -> _Projector | None:
        """Aynı kalibrasyon nesnesi için projektör (destek zarfı vb.) bir kez kurulur."""
        if calib is None:
            return None
        if self._proj is None or self._proj.calib is not calib:
            self._proj = _Projector(calib)
        return self._proj

    @staticmethod
    def _block_marks(proj: _Projector, calib: PitchCalibration, direction: int, lines: list[Line],
                     team: int) -> list[Mark]:
        L, W = calib.pitch_length_m, calib.pitch_width_m

        def x_of(depth: float) -> float:
            return depth if direction > 0 else L - depth

        def across(line: Line) -> np.ndarray | None:
            ys = np.linspace(max(0.0, line.y_min - LINE_MARGIN_M), min(W, line.y_max + LINE_MARGIN_M), 12)
            return proj.run(np.c_[np.full_like(ys, x_of(line.depth)), ys])

        out: list[Mark] = []
        drawn = [across(line) for line in lines[:2]]
        for pts in drawn:
            if pts is not None:
                out.append(Mark("line", tuple(map(tuple, pts.round(1).tolist())), team=team))
        if len(drawn) == 2 and drawn[0] is not None and drawn[1] is not None:
            back, front = lines[0], lines[1]
            out.append(Mark("band", tuple(map(tuple, np.vstack([drawn[0], drawn[1][::-1]]).round(1).tolist())),
                            team=team))
            y_mid = (max(back.y_min, front.y_min) + min(back.y_max, front.y_max)) / 2
            anchor = proj(np.array([[x_of((back.depth + front.depth) / 2), y_mid]]))
            if anchor is not None:
                out.append(Mark("label", (tuple(anchor[0].round(1).tolist()),), team=team,
                                text=f"{front.depth - back.depth:.0f} m"))
        return out


# --- çizim -----------------------------------------------------------------

# BGR: ev sahibi yeşil, deplasman kırmızı, atanmamış gri; vurgu (pres) sıcak kırmızı
TEAM_COLORS: dict[int | None, tuple[int, int, int]] = {0: (90, 200, 40), 1: (60, 80, 230), None: (170, 170, 170)}
EMPHASIS_COLOR = (40, 40, 235)


@lru_cache(maxsize=4)
def _font(size: int):
    from PIL import ImageFont

    path = os.environ.get("TELESTRATION_FONT") or str(_FONT_PATH)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _pill(bgr: np.ndarray, text: str, center: tuple[int, int], size: int,
          accent: tuple[int, int, int] | None = None) -> None:
    """Koyu, yuvarlak köşeli etiket (Türkçe karakterler için PIL ile); `accent`
    (BGR) verilirse solda o renkte nokta — etiketin hangi takımı anlattığı."""
    from PIL import Image, ImageDraw

    font = _font(size)
    x0, y0, x1, y1 = font.getbbox(text)
    pad = size // 2
    dot = size if accent is not None else 0
    x0 -= dot
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    left, top = int(center[0] - w / 2), int(center[1] - h / 2)
    H, Wd = bgr.shape[:2]
    left, top = max(0, min(left, Wd - w)), max(0, min(top, H - h))
    if w > Wd or h > H:
        return
    crop = bgr[top:top + h, left:left + w]
    img = Image.fromarray(crop[:, :, ::-1].copy())
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shade)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(28, 30, 34, 215),
                           outline=(255, 255, 255, 90), width=1)
    draw.text((pad - x0, pad - y0), text, font=font, fill=(255, 255, 255, 255))
    if accent is not None:
        r, cy = size * 0.3, h / 2
        draw.ellipse((pad, cy - r, pad + 2 * r, cy + r), fill=(accent[2], accent[1], accent[0], 255))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    bgr[top:top + h, left:left + w] = np.asarray(img)[:, :, ::-1]


def scaled(marks: list[Mark], factor: float) -> list[Mark]:
    """Görüntü küçültüldüğünde öğeleri aynı orana taşı (çizim küçük karede yapılır)."""
    return [Mark(m.kind, tuple((x * factor, y * factor) for x, y in m.points), m.team, m.emphasis, m.text)
            for m in marks]


def render(bgr: np.ndarray, marks: list[Mark]) -> None:
    """Çizim öğelerini kareye yerinde uygular (yarı saydam dolgular tek geçişte)."""
    import cv2

    fill = bgr.copy()
    for m in marks:
        pts = np.rint(m.points).astype(np.int32) if m.points else None
        if m.kind == "band":
            cv2.fillPoly(fill, [pts], (235, 235, 235))
        elif m.kind == "ring":
            color = EMPHASIS_COLOR if m.emphasis else TEAM_COLORS.get(m.team, TEAM_COLORS[None])
            cv2.fillPoly(fill, [pts], color)
    cv2.addWeighted(fill, 0.35, bgr, 0.65, 0, dst=bgr)
    scale = max(1, bgr.shape[1] // 960)
    for m in marks:
        if m.kind == "ring":
            color = EMPHASIS_COLOR if m.emphasis else TEAM_COLORS.get(m.team, TEAM_COLORS[None])
            cv2.polylines(bgr, [np.rint(m.points).astype(np.int32)], True, color,
                          (2 if m.emphasis else 1) * scale, cv2.LINE_AA)
        elif m.kind == "line":
            cv2.polylines(bgr, [np.rint(m.points).astype(np.int32)], False, (245, 245, 245), 2 * scale, cv2.LINE_AA)
        elif m.kind == "ball":
            cx, cy = (int(round(v)) for v in m.points[0])
            cv2.circle(bgr, (cx, cy), 6 * scale, (255, 255, 255), 2 * scale, cv2.LINE_AA)
    for m in marks:
        if m.kind == "label" and m.text:
            if m.points:
                _pill(bgr, m.text, (int(m.points[0][0]), int(m.points[0][1])), 14 * scale)
            else:
                _pill(bgr, m.text, (bgr.shape[1] // 2, int(bgr.shape[0] * 0.12)), 22 * scale,
                      accent=TEAM_COLORS.get(m.team))
