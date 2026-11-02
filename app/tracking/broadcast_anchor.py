"""Yayın karesinde tek kare çapa: doğru ailesi eşleştirme + DLT. Üretim hattına bağlı DEĞİL.

Ön kayıt: docs/measurements/broadcast-anchor-preregistration.json. Eşikler geliştirme
değerleridir, dondurulmadı. Izgara araması (`homography_fit.find_anchor`) yayın kadrajının
eğik duruşlarına ulaşamıyor: kusursuz çizgide bile 0/15 (daylight-calibration-funnel.json).
Burada duruş aranmaz, görüntüdeki doğrular model çizgileriyle eşlenip doğrudan çözülür:

1. Maskeden doğru parçaları → birleştirilmiş doğrular → açıya göre iki aile.
2. Aileden ikişer doğru × modelden ikişer çizgi: 4 kesişim, 4 nokta homografisi. Sıra
   korunur (görüntü solu küçük x, görüntü altı büyük y), yani TV kuralı atamanın içindedir.
3. Tek enine doğru görünen orta saha karelerinde orta yuvarlak elipsi ve orta çizgi kullanılır.
4. Tüm hipotezler toplu puanlanır, en iyiler iyileştirilir, kapılardan geçen tek kazanan alınır.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from app.tracking.homography_fit import (
    DEFAULT_TOLERANCE_PX,
    line_coverage,
    refine_homography,
    score_homography,
)
from app.tracking.pitch_model import PITCH_LENGTH_M, PITCH_WIDTH_M, model_points

MODEL_X_M = (0.0, 5.5, 16.5, 52.5, 88.5, 99.5, 105.0)
MODEL_Y_M = (0.0, 13.84, 24.84, 43.16, 54.16, 68.0)
CIRCLE_X_M = (52.5, 43.35, 61.65)
CIRCLE_Y_M = (24.85, 34.0, 43.15)
TOUCH_Y_M = (0.0, 68.0)

GRASS_HSV_LOW = (30, 40, 40)
GRASS_HSV_HIGH = (90, 255, 255)
LINE_THICKNESS_PX = 9
LOCAL_BG_WINDOW_PX = 61
LINE_CONTRAST_RATIO = 0.10
LINE_OTSU_FRACTION = 0.55
LINE_MIN_CONTRAST = 12
LINE_MIN_GRAY = 60
MAX_LINE_DENSITY = 0.08

MIN_SEGMENT_WIDTH_RATIO = 0.05   # ön kayıt: en kısa parça kare genişliğinin %5'i
HOUGH_VOTE_RATIO = 0.03
MAX_GAP_WIDTH_RATIO = 0.015
MERGE_ANGLE_DEG = 2.0
MERGE_OFFSET_PX = 8.0
MAX_LINES_PER_FAMILY = 6
# Sırt sınaması: saha çizgisi iki yanından parlak ince bir sırttır. Geliştirme 15 karede
# bulunan 397 doğrunun 297'si model çizgisi değildi; 0,5 eşiği doğruların %94'ünü tutuyor,
# sahtelerin %43'ünü atıyor.
RIDGE_MIN_SHARE = 0.5
RIDGE_MIN_RELATIVE = 0.08
RIDGE_SIDE_PX = 7
RIDGE_CENTRE_PX = 2
RIDGE_STEP_PX = 4.0
VANISHING_SINE = 0.03   # ~1,7° sapma
MIN_ELLIPSE_AXIS_RATIO = 0.08
MAX_ELLIPSE_RESIDUAL_PX = 3.0
MAX_ELLIPSE_COMPONENTS = 6

SCORE_STEP_M = 2.0
MIN_VISIBLE_AT_SCORE_STEP = 20
BATCH_SIZE = 4000
TOP_SCORED = 40
TOP_REFINED = 8

MIN_INLIER = 0.75
MIN_EXPLAINED = 0.60
MIN_LANDMARK_VISIBLE = 25
MIN_LANDMARK_INLIER = 0.70
WIN_MARGIN = 1.25
DISTINCT_M = 8.0
PHYSICAL_MARGIN_M = 5.0


@dataclass(frozen=True)
class ImageLine:
    """Görüntüde doğru: ax + by + c = 0, (a, b) birim; uçlar kırpma ve çizim içindir."""

    abc: tuple[float, float, float]
    p1: tuple[float, float]
    p2: tuple[float, float]
    length: float

    @property
    def angle_deg(self) -> float:
        return float(np.degrees(np.arctan2(self.p2[1] - self.p1[1], self.p2[0] - self.p1[0])) % 180.0)


@dataclass(frozen=True)
class BroadcastAnchor:
    homography: np.ndarray | None   # görüntü → saha; kabul yoksa None
    accepted: bool
    note: str
    inlier: float = 0.0
    explained: float = 0.0
    hypotheses: int = 0
    best_homography: np.ndarray | None = None   # kapıdan geçmese de en iyi duruş (teşhis)


def daylight_line_mask(bgr: np.ndarray) -> np.ndarray:
    """Yerel kontrast çizgi maskesi (commit 34c98e3 adayı): gölgedeki çizgiyi de bırakır.

    `pitch_lines.extract_lines` hash'li olduğu için burada ayrı durur. Doku doymuş karede boş döner.
    """
    import cv2

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array(GRASS_HSV_LOW), np.array(GRASS_HSV_HIGH))
    inside = cv2.morphologyEx(grass, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))) > 0
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (LINE_THICKNESS_PX, LINE_THICKNESS_PX))
    opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    thin = cv2.subtract(gray, opened)
    window = max(3, int(round(LOCAL_BG_WINDOW_PX * bgr.shape[1] / 1280.0)) | 1)
    relative = thin.astype(np.float32) / np.maximum(cv2.blur(opened, (window, window)).astype(np.float32), 1.0)
    if not inside.any():
        return np.zeros(gray.shape, dtype=bool)
    as_u8 = np.clip(relative * 255.0, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(as_u8[inside], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(LINE_CONTRAST_RATIO, LINE_OTSU_FRACTION * float(otsu) / 255.0)
    mask = (relative >= threshold) & (thin >= LINE_MIN_CONTRAST) & (gray >= LINE_MIN_GRAY) & inside
    if mask.sum() > MAX_LINE_DENSITY * inside.sum():
        return np.zeros(gray.shape, dtype=bool)
    return mask


def line_from_points(p1: np.ndarray, p2: np.ndarray) -> ImageLine:
    direction = p2 - p1
    length = float(np.hypot(*direction))
    a, b = -direction[1] / length, direction[0] / length
    c = -(a * p1[0] + b * p1[1])
    return ImageLine((float(a), float(b), float(c)), (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])), length)


def merge_segments(segments: np.ndarray) -> list[ImageLine]:
    """Aynı doğruya düşen parçaları uzundan kısaya birleştir; uçlar en uzak iz düşümler."""
    order = np.argsort(-np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1]))
    groups: list[tuple[ImageLine, list[np.ndarray]]] = []
    for seg in segments[order].astype(float):
        p1, p2 = seg[:2], seg[2:]
        cand = line_from_points(p1, p2)
        for base, points in groups:
            diff = abs(cand.angle_deg - base.angle_deg)
            if min(diff, 180.0 - diff) > MERGE_ANGLE_DEG:
                continue
            a, b, c = base.abc
            if max(abs(a * p[0] + b * p[1] + c) for p in (p1, p2)) <= MERGE_OFFSET_PX:
                points.extend([p1, p2])
                break
        else:
            groups.append((cand, [p1, p2]))
    out = []
    for _base, points in groups:
        pts = np.asarray(points)
        centre = pts.mean(axis=0)
        direction = np.linalg.svd(pts - centre)[2][0]
        along = (pts - centre) @ direction
        out.append(line_from_points(centre + along.min() * direction, centre + along.max() * direction))
    return sorted(out, key=lambda ln: -ln.length)


def ridge_share(gray: np.ndarray, line: ImageLine) -> float:
    """Doğru boyunca merkezi iki yanından belirgin parlak örneklerin payı (gölge kenarı sırt değildir)."""
    start, end = np.array(line.p1), np.array(line.p2)
    along = (end - start) / line.length
    normal = np.array([-along[1], along[0]])
    samples = start + np.arange(0.0, line.length, RIDGE_STEP_PX)[:, None] * along

    def values(offset: int) -> np.ndarray:
        at = samples + offset * normal
        u = np.clip(at[:, 0].astype(int), 0, gray.shape[1] - 1)
        v = np.clip(at[:, 1].astype(int), 0, gray.shape[0] - 1)
        return gray[v, u].astype(float)

    centre = np.max([values(o) for o in range(-RIDGE_CENTRE_PX, RIDGE_CENTRE_PX + 1)], axis=0)
    sides = np.maximum(values(-RIDGE_SIDE_PX), values(RIDGE_SIDE_PX))
    return float((((centre - sides) / np.maximum(sides, 1.0)) > RIDGE_MIN_RELATIVE).mean())


def detect_lines(mask: np.ndarray) -> list[ImageLine]:
    import cv2

    width = mask.shape[1]
    segments = cv2.HoughLinesP(
        mask.astype(np.uint8) * 255, 1, np.pi / 720, threshold=int(HOUGH_VOTE_RATIO * width),
        minLineLength=MIN_SEGMENT_WIDTH_RATIO * width, maxLineGap=MAX_GAP_WIDTH_RATIO * width,
    )
    if segments is None:
        return []
    return merge_segments(segments.reshape(-1, 4))


def _converging(lines: list[ImageLine], vanishing: np.ndarray) -> list[int]:
    """Kaçış noktasına yönelen doğruların sırası: orta noktadan noktaya yön ile doğru yönü."""
    out = []
    for i, ln in enumerate(lines):
        mid = (np.array(ln.p1) + np.array(ln.p2)) / 2.0
        toward = vanishing[:2] - mid * vanishing[2]
        norm = np.hypot(*toward)
        if norm < 1e-9:
            continue
        direction = (np.array(ln.p2) - np.array(ln.p1)) / ln.length
        sine = abs(direction[0] * toward[1] - direction[1] * toward[0]) / norm
        if sine <= VANISHING_SINE:
            out.append(i)
    return out


def _best_family(lines: list[ImageLine], size: tuple[int, int]) -> list[int]:
    """Toplam boyu en büyük, kaçış noktası kadraj dışında kalan doğru kümesi."""
    w, h = size
    best: list[int] = []
    best_length = 0.0
    for a, b in combinations(lines, 2):
        vanishing = np.cross(a.abc, b.abc)
        if abs(vanishing[2]) > 1e-9:
            x, y = vanishing[:2] / vanishing[2]
            if 0.0 <= x <= w and 0.0 <= y <= h:
                continue
        members = _converging(lines, vanishing)
        length = sum(lines[i].length for i in members)
        if len(members) >= 2 and length > best_length:
            best, best_length = members, length
    return best


def split_families(lines: list[ImageLine], size: tuple[int, int]) -> tuple[list[ImageLine], list[ImageLine]]:
    """İki kaçış noktası: saha çizgileri perspektifte yelpazelenir, açı kümesi bunu bölüyor.

    Hiçbir aileye girmeyenler (yayın düz görünen parçaları) atılır.
    """
    first = _best_family(lines, size)
    chosen = set(first)
    rest = [ln for i, ln in enumerate(lines) if i not in chosen]
    second = _best_family(rest, size)
    if second:
        return [lines[i] for i in first], [rest[i] for i in second]
    return [lines[i] for i in first], rest


def intersect(l1: ImageLine, l2: ImageLine) -> np.ndarray | None:
    p = np.cross(l1.abc, l2.abc)
    if abs(p[2]) < 1e-9:
        return None
    return p[:2] / p[2]


def _ordered(family: list[ImageLine], reference: ImageLine, axis: int) -> list[ImageLine]:
    """Aileyi referans doğru boyunca sırala: 0 = soldan sağa, 1 = yukarıdan aşağıya."""
    keyed = []
    for ln in family:
        p = intersect(ln, reference)
        if p is not None:
            keyed.append((float(p[axis]), ln))
    keyed.sort(key=lambda item: item[0])
    return [ln for _key, ln in keyed]


def grid_correspondences(lengthwise: list[ImageLine], crosswise: list[ImageLine]) -> tuple[np.ndarray, np.ndarray]:
    """(N,4,2) görüntü ve (N,4,2) saha noktaları: boyuna y = sabit, enine x = sabit doğrular."""
    empty = np.empty((0, 4, 2)), np.empty((0, 4, 2))
    if len(lengthwise) < 2 or len(crosswise) < 2:
        return empty
    along = _ordered(lengthwise[:MAX_LINES_PER_FAMILY], crosswise[0], 1)
    across = _ordered(crosswise[:MAX_LINES_PER_FAMILY], lengthwise[0], 0)
    images, pitches = [], []
    model_pairs = [(ya, yb, xa, xb) for ya, yb in combinations(MODEL_Y_M, 2) for xa, xb in combinations(MODEL_X_M, 2)]
    template = np.array([[[xa, ya], [xb, ya], [xa, yb], [xb, yb]] for ya, yb, xa, xb in model_pairs])
    for la, lb in combinations(along, 2):
        for ta, tb in combinations(across, 2):
            corners = [intersect(la, ta), intersect(la, tb), intersect(lb, ta), intersect(lb, tb)]
            if any(c is None for c in corners):
                continue
            images.append(np.repeat(np.asarray(corners)[None], len(template), axis=0))
            pitches.append(template)
    if not images:
        return empty
    return np.concatenate(images), np.concatenate(pitches)


def _conic_from_box(box: tuple) -> np.ndarray:
    (cx, cy), (d1, d2), angle = box
    t = np.radians(angle)
    rot = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    q = rot @ np.diag([4.0 / d1 ** 2, 4.0 / d2 ** 2]) @ rot.T
    centre = np.array([cx, cy])
    conic = np.eye(3)
    conic[:2, :2] = q
    conic[:2, 2] = conic[2, :2] = -q @ centre
    conic[2, 2] = centre @ q @ centre - 1.0
    return conic


def detect_ellipses(mask: np.ndarray, lines: list[ImageLine]) -> list[np.ndarray]:
    """Doğrular silinince kalan yay bileşenlerinden elips konikleri (tek ve ikili bileşen)."""
    import cv2

    rest = mask.astype(np.uint8).copy()
    for ln in lines:
        p1, p2 = np.round(ln.p1).astype(int), np.round(ln.p2).astype(int)
        cv2.line(rest, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 0, 9)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    biggest = (np.argsort(-areas)[:MAX_ELLIPSE_COMPONENTS] + 1).tolist() if count > 1 else []
    parts = [np.column_stack(np.nonzero(labels == i)[::-1]).astype(np.float32)[::3] for i in biggest
             if stats[i, cv2.CC_STAT_AREA] >= 40]
    groups = [[p] for p in parts] + [[a, b] for a, b in combinations(parts, 2)]
    conics: list[tuple[int, np.ndarray]] = []
    min_axis = MIN_ELLIPSE_AXIS_RATIO * mask.shape[1]
    for group in groups:
        pts = np.concatenate(group)
        if len(pts) < 8:
            continue
        box = cv2.fitEllipse(pts)
        d1, d2 = box[1]
        if min(d1, d2) < 1e-3 or max(d1, d2) < min_axis:
            continue
        conic = _conic_from_box(box)
        hom = np.column_stack([pts, np.ones(len(pts))])
        radial = np.sqrt(np.maximum(np.sum((hom @ conic) * hom, axis=1) + 1.0, 0.0))
        if np.median(np.abs(radial - 1.0)) * max(d1, d2) / 2.0 > MAX_ELLIPSE_RESIDUAL_PX:
            continue
        conics.append((len(pts), conic))
    conics.sort(key=lambda item: -item[0])
    return [c for _n, c in conics[:MAX_ELLIPSE_COMPONENTS]]


def line_conic_points(line: np.ndarray, conic: np.ndarray) -> np.ndarray | None:
    """Doğru ile koniğin iki kesişimi; görüntüde yukarıdan aşağıya (eşitse soldan sağa)."""
    a, b, c = line
    norm = a * a + b * b
    p0 = np.array([-a * c / norm, -b * c / norm, 1.0])
    d = np.array([-b, a, 0.0])
    qa, qb, qc = d @ conic @ d, 2.0 * p0 @ conic @ d, p0 @ conic @ p0
    disc = qb * qb - 4.0 * qa * qc
    if abs(qa) < 1e-15 or disc <= 0.0:
        return None
    roots = (-qb + np.array([-1.0, 1.0]) * np.sqrt(disc)) / (2.0 * qa)
    points = np.array([p0[:2] + s * d[:2] for s in roots])
    return points[np.lexsort((points[:, 0], points[:, 1]))]


def circle_correspondences(lines: list[ImageLine], conics: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Orta yuvarlak + orta çizgi: koniğin kutbu boyuna kaçış noktasını, taç kesişimi merkezi verir.

    Orta çizgi üstünde üç bilinen y (iki elips kesişimi + taç) 1B izdüşümü belirler; y = 34
    merkezdir. Taç yoksa elips merkezinin iz düşümü yaklaşık merkez olur, iyileştirme düzeltir.
    """
    pitch = np.array([[CIRCLE_X_M[0], CIRCLE_Y_M[0]], [CIRCLE_X_M[0], CIRCLE_Y_M[2]],
                      [CIRCLE_X_M[1], CIRCLE_Y_M[1]], [CIRCLE_X_M[2], CIRCLE_Y_M[1]]])
    images = []
    for conic in conics:
        inverse = np.linalg.inv(conic)
        ellipse_centre = inverse[:2, 2] / inverse[2, 2]
        for centre_line in lines:
            ends = line_conic_points(np.array(centre_line.abc), conic)
            if ends is None:
                continue
            far, near = ends
            direction = (near - far) / np.hypot(*(near - far))
            vanishing = inverse @ np.array(centre_line.abc)
            centres = [far + direction * (float((ellipse_centre - far) @ direction))]
            for touch in lines:
                if touch is centre_line:
                    continue
                q = intersect(touch, centre_line)
                if q is None:
                    continue
                t_q = float((q - far) @ direction)
                t_near = float((near - far) @ direction)
                if 0.0 <= t_q <= t_near:
                    continue
                y_q = TOUCH_Y_M[0] if t_q < 0.0 else TOUCH_Y_M[1]
                centres.append(far + direction * _centre_on_line(t_q, y_q, t_near))
            for centre in centres:
                through = np.cross(np.append(centre, 1.0), vanishing)
                sides = line_conic_points(through, conic)
                if sides is None:
                    continue
                sides = sides[np.argsort(sides[:, 0])]
                images.append(np.array([far, near, sides[0], sides[1]]))
    if not images:
        return np.empty((0, 4, 2)), np.empty((0, 4, 2))
    return np.asarray(images), np.repeat(pitch[None], len(images), axis=0)


def _centre_on_line(t_q: float, y_q: float, t_near: float) -> float:
    """t = 0 → y 24.85, t_near → y 43.15, t_q → y_q: 1B izdüşümde y = 34'ün t'si."""
    known_t = np.array([0.0, t_near, t_q])
    known_y = np.array([CIRCLE_Y_M[0], CIRCLE_Y_M[2], y_q])
    # y = (αt + β) / (γt + 1)
    system = np.column_stack([known_t, np.ones(3), -known_t * known_y])
    alpha, beta, gamma = np.linalg.solve(system, known_y)
    return float((CIRCLE_Y_M[1] - beta) / (alpha - gamma * CIRCLE_Y_M[1]))


def solve_pitch_to_image(image: np.ndarray, pitch: np.ndarray) -> np.ndarray:
    """(N,4,2) karşılıklardan (N,3,3) saha → görüntü homografisi; tekil olanlar NaN."""
    n = len(image)
    src, dst = pitch / 100.0, image / 1000.0
    a = np.zeros((n, 8, 8))
    b = dst.reshape(n, 8)
    a[:, 0::2, 0:2] = src
    a[:, 0::2, 2] = 1.0
    a[:, 1::2, 3:5] = src
    a[:, 1::2, 5] = 1.0
    a[:, 0::2, 6:8] = -src * dst[:, :, :1]
    a[:, 1::2, 6:8] = -src * dst[:, :, 1:]
    out = np.full((n, 3, 3), np.nan)
    finite = np.isfinite(a).all(axis=(1, 2)) & np.isfinite(b).all(axis=1)
    ok = np.zeros(n, dtype=bool)
    ok[finite] = np.abs(np.linalg.det(a[finite])) > 1e-14
    if ok.any():
        h = np.linalg.solve(a[ok], b[ok][..., None])[..., 0]
        out[ok] = np.concatenate([h, np.ones((len(h), 1))], axis=1).reshape(-1, 3, 3)
    scale_img = np.diag([1000.0, 1000.0, 1.0])
    scale_pitch = np.diag([0.01, 0.01, 1.0])
    return scale_img @ out @ scale_pitch


def score_batch(g: np.ndarray, dist_map: np.ndarray, pts: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    """(N,) doğru düşen ve (N,) kadraja düşen model noktası sayısı. Kamera arkası geçersizdir."""
    h_img, w_img = dist_map.shape
    hom = np.column_stack([pts, np.ones(len(pts))])
    hits, visible = [], []
    for start in range(0, len(g), BATCH_SIZE):
        proj = g[start:start + BATCH_SIZE] @ hom.T
        w = proj[:, 2, :]
        with np.errstate(divide="ignore", invalid="ignore"):
            u, v = proj[:, 0, :] / w, proj[:, 1, :] / w
        same_side = (w > 0).all(axis=1) | (w < 0).all(axis=1)
        inside = np.isfinite(u) & np.isfinite(v) & (u >= 0) & (u < w_img) & (v >= 0) & (v < h_img)
        inside &= same_side[:, None]
        near = np.zeros_like(inside)
        near[inside] = dist_map[v[inside].astype(int), u[inside].astype(int)] <= tolerance
        hits.append(near.sum(axis=1))
        visible.append(inside.sum(axis=1))
    return np.concatenate(hits), np.concatenate(visible)


def physically_valid(h_img_to_pitch: np.ndarray, size: tuple[int, int]) -> bool:
    """Kadrajın alt yarısı saha + pay içinde ve yönelim TV kuralına uyuyor (sol küçük x, alt büyük y)."""
    w, h = size
    probes = np.array([[w * fx, h * fy, 1.0] for fx in (0.25, 0.5, 0.75) for fy in (0.6, 0.8)])
    q = probes @ h_img_to_pitch.T
    if np.any(np.abs(q[:, 2]) < 1e-9):
        return False
    p = q[:, :2] / q[:, 2:3]
    m = PHYSICAL_MARGIN_M
    if not ((p[:, 0] >= -m).all() and (p[:, 0] <= PITCH_LENGTH_M + m).all()
            and (p[:, 1] >= -m).all() and (p[:, 1] <= PITCH_WIDTH_M + m).all()):
        return False
    grid = p.reshape(3, 2, 2)
    return bool((grid[1:, :, 0] > grid[:-1, :, 0]).all() and (grid[:, 1, 1] > grid[:, 0, 1]).all())


def _segment_mask(lines: list[ImageLine], shape: tuple[int, int]) -> np.ndarray:
    import cv2

    canvas = np.zeros(shape, np.uint8)
    for ln in lines:
        p1, p2 = np.round(ln.p1).astype(int), np.round(ln.p2).astype(int)
        cv2.line(canvas, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 1, 1)
    return canvas > 0


def _distance(h_a: np.ndarray, h_b: np.ndarray, size: tuple[int, int]) -> float:
    w, h = size
    probes = np.array([[w * fx, h * fy, 1.0] for fx in (0.25, 0.5, 0.75) for fy in (0.45, 0.6, 0.75)])
    a, b = probes @ h_a.T, probes @ h_b.T
    return float(np.hypot(*((a[:, :2] / a[:, 2:3]) - (b[:, :2] / b[:, 2:3])).T).max())


def find_broadcast_anchor(
    mask: np.ndarray, gray: np.ndarray | None = None, tolerance_px: float | None = None,
) -> BroadcastAnchor:
    """Çizgi maskesinden çapa. Kapılardan geçen tek kazanan yoksa homografi dönmez.

    `gray` verilirse sırt sınamasını geçmeyen doğrular elenir; kusursuz maskede gerekmez.
    """
    import cv2

    shape = mask.shape[:2]
    size = (shape[1], shape[0])
    tol = tolerance_px if tolerance_px is not None else DEFAULT_TOLERANCE_PX * size[0] / 1280.0
    lines = detect_lines(mask)
    if gray is not None:
        lines = [ln for ln in lines if ridge_share(gray, ln) >= RIDGE_MIN_SHARE]
    if len(lines) < 2:
        return BroadcastAnchor(None, False, "yeterli doğru yok")
    fam_a, fam_b = split_families(lines, size)
    images, pitches = [], []
    for lengthwise, crosswise in ((fam_a, fam_b), (fam_b, fam_a)):
        img, pit = grid_correspondences(lengthwise, crosswise)
        images.append(img)
        pitches.append(pit)
    img, pit = circle_correspondences(lines, detect_ellipses(mask, lines))
    images.append(img)
    pitches.append(pit)
    all_img, all_pit = np.concatenate(images), np.concatenate(pitches)
    total = len(all_img)
    if total == 0:
        return BroadcastAnchor(None, False, "hipotez kurulamadı")

    dist_map = cv2.distanceTransform((~mask.astype(bool)).astype(np.uint8), cv2.DIST_L2, 3)
    g = solve_pitch_to_image(all_img, all_pit)
    valid = np.isfinite(g).all(axis=(1, 2))
    g = g[valid]
    if len(g) == 0:
        return BroadcastAnchor(None, False, "hipotezlerin hepsi tekil", hypotheses=total)
    hits, visible = score_batch(g, dist_map, model_points(SCORE_STEP_M), tol)
    key = (hits - (visible - hits)).astype(float)
    key[visible < MIN_VISIBLE_AT_SCORE_STEP] = -np.inf
    order = np.argsort(-key)

    seg_mask = _segment_mask(lines, shape)
    scored: list[tuple[float, np.ndarray]] = []
    for i in order:
        if not np.isfinite(key[i]) or len(scored) >= TOP_SCORED:
            break
        try:
            h = np.linalg.inv(g[i])
        except np.linalg.LinAlgError:
            continue
        if physically_valid(h, size):
            scored.append((float(key[i]), h / h[2, 2]))
    if not scored:
        return BroadcastAnchor(None, False, "fiziksel kapıyı geçen hipotez yok", hypotheses=total)

    refined: list[tuple[float, np.ndarray, float, float]] = []
    picked: list[np.ndarray] = []
    for _key, h in scored:
        if any(_distance(h, other, size) < 1.0 for other in picked):
            continue
        picked.append(h)
        if len(picked) > TOP_REFINED:
            break
        fit = refine_homography(h, dist_map, tolerance_px=tol, step_px=4.0)
        pose = fit.homography if physically_valid(fit.homography, size) else h
        _s, inlier, _v = score_homography(pose, dist_map, pts_m=model_points(1.0), tolerance_px=tol)
        explained = line_coverage(pose, seg_mask, tolerance_px=2.0 * tol)
        refined.append((inlier * explained, pose, inlier, explained))
    refined.sort(key=lambda item: -item[0])
    best_key, best, inlier, explained = refined[0]

    def reject(note: str) -> BroadcastAnchor:
        return BroadcastAnchor(None, False, note, round(inlier, 3), round(explained, 3), total, best)

    runner = next((k for k, h, _i, _e in refined[1:] if _distance(h, best, size) >= DISTINCT_M), 0.0)
    _s, lm_inlier, lm_visible = score_homography(best, dist_map, pts_m=model_points(1.0, "landmark"), tolerance_px=tol)
    if lm_visible < MIN_LANDMARK_VISIBLE:
        return reject(f"ayırt edici yapı görünmüyor ({lm_visible} nokta)")
    if lm_inlier < MIN_LANDMARK_INLIER:
        return reject(f"ayırt edici yapı oturmadı (%{lm_inlier * 100:.0f})")
    if inlier < MIN_INLIER:
        return reject(f"inlier düşük (%{inlier * 100:.0f})")
    if explained < MIN_EXPLAINED:
        return reject(f"doğruların açıklanan payı düşük (%{explained * 100:.0f})")
    if runner > 0.0 and best_key < runner * WIN_MARGIN:
        return reject("sahne belirsiz: uzak rakip belirgin geçilemedi")
    return BroadcastAnchor(best, True, "kabul", round(inlier, 3), round(explained, 3), total, best)
