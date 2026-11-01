"""Üstten 2D maç görünümü (ör. Football Manager 2D) → oyuncu/top konumu.

Ekran yakalamadan gelen RGB karede saha yeşil bir dikdörtgendir; oyuncular takım
renginde dairelerdir, top küçük açık renkli bir noktadır. Kamera sabit ve üstten
baktığı için kalibrasyon saha dikdörtgeninin kendisidir (doğrusal eşleme).

Yalnız numpy kullanır (CI'da OpenCV yok). Adımlar:

1. **Saha** — yeşil piksel oranı yüksek satır/sütunların en uzun ardışık bloğu
   (`find_pitch`); operatör dikdörtgeni elle de verebilir.
2. **Daireler** — saha içinde yeşil olmayan pikseller, çizgileri silmek için
   aşındırılır (çizgi 2–3 px, daire çok daha kalın), bağlı bileşenler; boyut
   ve doluluk süzgeci. Daire boyutu sabit değil: kompakt bileşenlerin medyan
   alanına göre uyarlanır.
3. **Top** — açık renkli (beyaz/sarı) küçük, kompakt bileşen; çizgiler ince
   ve uzun olduğu için elenir.
4. **Takım** — dairelerin medyan rengi iki takım merkezine atanır
   (`TeamPalette`; ilk karede k-ortalama, sonra sabit). Merkeze uzak renk
   (kaleci, hakem) takıma atanmaz.

Sınır: görüntü ölçeğine ve FM temasına göre eşikler sezgiseldir; gerçek ekran
görüntüsüyle ayarlanmalı (`scripts.fm_capture --image ... --debug`). Bu kaynak
yalnız deneme ortamıdır: gerçek video doğruluğu hakkında bir şey kanıtlamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

GREEN_MIN = 60
GREEN_MARGIN = 15
PITCH_ROW_SHARE = 0.45        # bir satır/sütun bu oranda yeşilse sahaya aittir
LINE_EROSION_PX = 2           # çizgileri silen aşındırma yarıçapı
MIN_DISC_AREA_PX = 12
DISC_AREA_RANGE = (0.35, 2.6)  # medyan disk alanına göre kabul aralığı
MIN_FILL = 0.45               # bileşen alanı / sınırlayıcı kutu alanı
MAX_ASPECT = 1.8
BALL_AREA_RANGE_PX = (4, 80)
BRIGHT_MIN = 190
BALL_MAX_FULL_PX = 150      # aşındırmadan önceki bileşen bundan büyükse çizgidir
TEAM_COLOR_MAX_DIST = 70.0    # RGB uzaklığı; üstü takıma atanmaz (kaleci/hakem)
MAX_FOREGROUND_PX = 250_000


@dataclass(frozen=True)
class PitchRect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def to_pct(self, cx: float, cy: float) -> tuple[float, float]:
        """Piksel → saha yüzdesi (0–100, x uzun kenar)."""
        x = (cx - self.x0) / max(self.width, 1) * 100.0
        y = (cy - self.y0) / max(self.height, 1) * 100.0
        return float(np.clip(x, 0.0, 100.0)), float(np.clip(y, 0.0, 100.0))


@dataclass(frozen=True)
class Blob:
    cx: float
    cy: float
    area: int
    color: tuple[float, float, float]


@dataclass(frozen=True)
class Detection:
    players: list[tuple[int | None, float, float]]   # (takım 0/1/None, x %, y %)
    ball: tuple[float, float] | None
    pitch: PitchRect


def green_mask(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    return (g >= GREEN_MIN) & (g > r + GREEN_MARGIN) & (g > b + GREEN_MARGIN)


def _longest_run(flags: np.ndarray, max_gap: int = 0) -> tuple[int, int] | None:
    """En uzun True bloğu; `max_gap` uzunluğa kadar False boşluğu bloğu bölmez
    (saha içindeki dikey/yatay beyaz çizgi satırı ya da sütunu)."""
    best: tuple[int, int] | None = None
    start = last = None
    for i, f in enumerate([*flags.tolist(), *([False] * (max_gap + 1))]):
        if f:
            if start is None:
                start = i
            last = i
        elif start is not None and last is not None and i - last > max_gap:
            if best is None or last + 1 - start > best[1] - best[0]:
                best = (start, last + 1)
            start = last = None
    return best


def find_pitch(rgb: np.ndarray) -> PitchRect | None:
    g = green_mask(rgb)
    gap = max(3, min(rgb.shape[:2]) // 100)
    rows = _longest_run(g.mean(axis=1) >= PITCH_ROW_SHARE, gap)
    cols = _longest_run(g.mean(axis=0) >= PITCH_ROW_SHARE, gap)
    if rows is None or cols is None or rows[1] - rows[0] < 20 or cols[1] - cols[0] < 20:
        return None
    return PitchRect(cols[0], rows[0], cols[1], rows[1])


def erode(mask: np.ndarray, radius: int) -> np.ndarray:
    """Kare yapı elemanlı ikili aşındırma (numpy kaydırma)."""
    out = mask.copy()
    for _ in range(radius):
        m = out
        shrunk = m.copy()
        shrunk[1:, :] &= m[:-1, :]
        shrunk[:-1, :] &= m[1:, :]
        shrunk[:, 1:] &= m[:, :-1]
        shrunk[:, :-1] &= m[:, 1:]
        out = shrunk
    return out


def label(mask: np.ndarray) -> list[np.ndarray]:
    """4-komşulu bağlı bileşenler → her biri (N, 2) [satır, sütun] dizisi."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    if len(ys) > MAX_FOREGROUND_PX:
        raise ValueError("ön plan çok büyük — saha dikdörtgeni yanlış olabilir")
    width = mask.shape[1]
    keys = (ys.astype(np.int64) * width + xs).tolist()
    index = dict(zip(keys, range(len(keys)), strict=True))
    seen = np.zeros(len(keys), dtype=bool)
    comps = []
    for i in range(len(keys)):
        if seen[i]:
            continue
        stack = [i]
        seen[i] = True
        members = []
        while stack:
            j = stack.pop()
            members.append(j)
            k = keys[j]
            y, x = divmod(k, width)
            for nk in ((k - width) if y > 0 else -1, (k + width), (k - 1) if x > 0 else -1,
                       (k + 1) if x < width - 1 else -1):
                n = index.get(nk) if nk >= 0 else None
                if n is not None and not seen[n]:
                    seen[n] = True
                    stack.append(n)
        idx = np.array(members)
        comps.append(np.stack([ys[idx], xs[idx]], axis=1))
    return comps


def _compact(comp: np.ndarray) -> bool:
    h = int(comp[:, 0].max() - comp[:, 0].min()) + 1
    w = int(comp[:, 1].max() - comp[:, 1].min()) + 1
    return len(comp) / (h * w) >= MIN_FILL and max(h, w) / max(min(h, w), 1) <= MAX_ASPECT


def _blob(comp: np.ndarray, rgb: np.ndarray, dy: int, dx: int) -> Blob:
    colors = rgb[comp[:, 0], comp[:, 1]].astype(float)
    med = np.median(colors, axis=0)
    return Blob(float(comp[:, 1].mean()) + dx, float(comp[:, 0].mean()) + dy, len(comp),
                (float(med[0]), float(med[1]), float(med[2])))


def find_discs(rgb: np.ndarray, pitch: PitchRect) -> list[Blob]:
    crop = rgb[pitch.y0:pitch.y1, pitch.x0:pitch.x1]
    fg = erode(~green_mask(crop), LINE_EROSION_PX)
    comps = [c for c in label(fg) if len(c) >= MIN_DISC_AREA_PX and _compact(c)]
    if not comps:
        return []
    typical = float(np.median([len(c) for c in comps]))
    lo, hi = DISC_AREA_RANGE
    return [_blob(c, crop, pitch.y0, pitch.x0) for c in comps if lo * typical <= len(c) <= hi * typical]


def find_ball(rgb: np.ndarray, pitch: PitchRect, discs: list[Blob]) -> tuple[float, float] | None:
    """Disk olmayan, küçük, açık renkli, en daire-benzeri bileşen (çizgi kırıntıları
    uzun ya da seyrek olduğu için daire benzerliğinde kaybeder)."""
    crop = rgb[pitch.y0:pitch.y1, pitch.x0:pitch.x1].astype(np.int16)
    bright = (crop.min(axis=2) >= BRIGHT_MIN - 60) & (crop.max(axis=2) >= BRIGHT_MIN) & ~green_mask(crop)
    # aşındırmadan ÖNCEKİ bileşeni büyük olan aday çizgi ağının parçasıdır
    # (orta yuvarlak × orta çizgi kesişimi aşındırmadan sonra top gibi görünür)
    full_size = np.zeros(bright.shape, dtype=np.int32)
    for c in label(bright):
        full_size[c[:, 0], c[:, 1]] = len(c)
    bright = erode(bright, 1)
    radius = np.sqrt(np.median([d.area for d in discs]) / np.pi) if discs else 6.0
    best: tuple[float, float, float] | None = None
    for c in label(bright):
        if not BALL_AREA_RANGE_PX[0] <= len(c) <= BALL_AREA_RANGE_PX[1] or not _compact(c):
            continue
        if full_size[c[0, 0], c[0, 1]] > BALL_MAX_FULL_PX:
            continue
        cx, cy = float(c[:, 1].mean()) + pitch.x0, float(c[:, 0].mean()) + pitch.y0
        # disk içindeki forma numarası top değildir
        if any(np.hypot(cx - d.cx, cy - d.cy) < radius for d in discs):
            continue
        h = int(np.ptp(c[:, 0])) + 1
        w = int(np.ptp(c[:, 1])) + 1
        score = abs(len(c) / (h * w) - np.pi / 4) + 0.5 * (max(h, w) / min(h, w) - 1.0)
        if best is None or score < best[2]:
            best = (cx, cy, score)
    return (best[0], best[1]) if best else None


def _kmeans(colors: np.ndarray, k: int, iters: int = 20) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(colors.sum(axis=1))
    centers = colors[order[np.linspace(0, len(colors) - 1, k).astype(int)]].copy()
    assign = np.zeros(len(colors), dtype=int)
    for _ in range(iters):
        assign = np.argmin(((colors[:, None, :] - centers[None]) ** 2).sum(axis=2), axis=1)
        for j in range(k):
            if np.any(assign == j):
                centers[j] = colors[assign == j].mean(axis=0)
    return centers, assign


@dataclass
class TeamPalette:
    """İki takım rengi; ilk yeterli karede öğrenilir, sonra sabit kalır."""

    centers: np.ndarray | None = None
    max_dist: float = TEAM_COLOR_MAX_DIST
    swap: bool = False
    home_hint: tuple[float, float, float] | None = None
    learned_from: int = field(default=0)

    def fit(self, blobs: list[Blob]) -> bool:
        if len(blobs) < 8:
            return False
        colors = np.array([b.color for b in blobs])
        k = min(4, len(blobs))
        centers, assign = _kmeans(colors, k)
        sizes = np.bincount(assign, minlength=k)
        teams = centers[np.argsort(-sizes)[:2]]
        if self.home_hint is not None:
            hint = np.array(self.home_hint)
            if np.linalg.norm(teams[1] - hint) < np.linalg.norm(teams[0] - hint):
                teams = teams[::-1]
        if self.swap:
            teams = teams[::-1]
        self.centers = teams
        self.learned_from = len(blobs)
        return True

    def assign(self, blob: Blob) -> int | None:
        if self.centers is None:
            return None
        d = np.linalg.norm(self.centers - np.array(blob.color), axis=1)
        j = int(np.argmin(d))
        return j if d[j] <= self.max_dist else None


def detect(rgb: np.ndarray, palette: TeamPalette, pitch: PitchRect | None = None) -> Detection | None:
    """Tek kare. Saha bulunamazsa None."""
    rect = pitch or find_pitch(rgb)
    if rect is None:
        return None
    discs = find_discs(rgb, rect)
    if palette.centers is None:
        palette.fit(discs)
    players = [(palette.assign(d), *rect.to_pct(d.cx, d.cy)) for d in discs]
    ball_px = find_ball(rgb, rect, discs)
    ball = rect.to_pct(*ball_px) if ball_px else None
    return Detection(players=players, ball=ball, pitch=rect)


POSSESSION_RADIUS_PCT = 3.0   # topa bu kadar yakın (saha yüzdesi, ~3 m) oyuncu sahiptir


def nearest_owner(det: Detection) -> int | None:
    if det.ball is None:
        return None
    bx, by = det.ball
    best = min(((np.hypot(x - bx, (y - by) * 68 / 105), t) for t, x, y in det.players if t is not None),
               default=None)
    return best[1] if best is not None and best[0] <= POSSESSION_RADIUS_PCT else None
