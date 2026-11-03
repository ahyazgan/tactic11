"""Kamera önselli yayın çapası: çapa reddedince maçın kamera konumuyla ikinci karar. Üretime bağlı değildir.

Ön kayıt: docs/measurements/broadcast-anchor-camera-prior-preregistration.json.

Ana kamera sabit bir noktada döner ve zoom yapar. Konum maçın kendi duruşlarından bulunduğu için yöntem
yalnız maç sonrası çalışır. Konum bilinince duruş 3 serbestliktir: kadraj merkezinin sahadaki hedefi + odak.
Tek kare çapanın kabulü değişmez; yalnız reddettiği karede aday kapısından geçen duruş çapa olur.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from app.tracking.broadcast_anchor import (
    MIN_VISIBLE_AT_SCORE_STEP,
    RIDGE_MIN_SHARE,
    SCORE_STEP_M,
    TOP_REFINED,
    BroadcastAnchor,
    _distance,
    _segment_mask,
    detect_lines,
    find_broadcast_anchor,
    physically_valid,
    ridge_share,
    score_batch,
)
from app.tracking.homography_fit import (
    DEFAULT_TOLERANCE_PX,
    line_coverage,
    refine_homography,
    score_homography,
)
from app.tracking.pitch_model import model_points

MAX_RESIDUAL_M = 1.0
MIN_INLIER = 0.6
MIN_EXPLAINED = 0.6
MIN_POSES = 10

SEARCH_POSES = 40
SEARCH_STEPS_M = (8.0, 4.0, 2.0, 1.0, 0.5)
MIN_HEIGHT_M = 5.0
RESIDUAL_FOCALS_PX = np.geomspace(800, 16000, 90)

GRID_FOCALS_PX = np.geomspace(1000, 10000, 20)
GRID_X_M = (-5.0, 110.0)
GRID_Y_M = (-5.0, 73.0)
COARSE_TOLERANCE_PX = 30.0
MIN_PICK_DISTANCE_M = 3.0
PICK_LIMIT = 300
REFINE_STEP_PX = 4.0


def camera_position(pose: np.ndarray, size: tuple[int, int]) -> np.ndarray | None:
    """Görüntü→saha duruşundan kamera merkezi (x, y, yükseklik; m). Kare piksel, ana nokta merkezde."""
    width, height = size
    to_center = np.array([[1, 0, -width / 2], [0, 1, -height / 2], [0, 0, 1.0]])
    h1, h2, h3 = (to_center @ np.linalg.inv(pose)).T
    den = h1[2] * h2[2]
    if abs(den) < 1e-15 or -(h1[0] * h2[0] + h1[1] * h2[1]) / den <= 0:
        return None
    focal = float(np.sqrt(-(h1[0] * h2[0] + h1[1] * h2[1]) / den))
    k_inv = np.diag([1 / focal, 1 / focal, 1.0])
    r1, r2, t = k_inv @ h1, k_inv @ h2, k_inv @ h3
    scale = 1 / np.sqrt(np.linalg.norm(r1) * np.linalg.norm(r2))
    center = -np.c_[r1 * scale, r2 * scale, np.cross(r1 * scale, r2 * scale)].T @ (t * scale)
    return np.array([center[0], center[1], abs(center[2])])


def pose_residual_m(pose: np.ndarray, camera: np.ndarray, size: tuple[int, int]) -> float | None:
    """Bu kameradan en iyi dönme+zoom ile duruşun saha noktalarına medyan uzaklık; geçersiz duruşta None."""
    width, height = size
    xs, ys = np.meshgrid(np.linspace(0.1, 0.9, 7) * width, np.linspace(0.4, 0.95, 5) * height)
    grid = np.c_[xs.ravel(), ys.ravel()]
    mapped = np.c_[grid, np.ones(len(grid))] @ pose.T
    pitch = mapped[:, :2] / mapped[:, 2:3]
    if not np.isfinite(pitch).all():
        return None
    # Görüntü y aşağı: sağ elli saha çerçevesinde yükseklik eksi z
    center = np.array([camera[0], camera[1], -abs(camera[2])])
    to_pitch = np.c_[pitch, np.zeros(len(pitch))] - center
    to_pitch /= np.linalg.norm(to_pitch, axis=1, keepdims=True)
    centered = grid - np.array([width / 2, height / 2])
    best = None
    for focal in RESIDUAL_FOCALS_PX:
        rays = np.c_[centered / focal, np.ones(len(centered))]
        rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        u, _, vt = np.linalg.svd(rays.T @ to_pitch)
        rotated = rays @ (u @ np.diag([1, 1, np.sign(np.linalg.det(u @ vt))]) @ vt)
        reach = -center[2] / np.where(np.abs(rotated[:, 2]) < 1e-6, -1e-6, rotated[:, 2])
        hit = center[:2] + rotated[:, :2] * reach[:, None]
        error = float(np.median(np.hypot(*(hit - pitch).T)))
        if best is None or error < best:
            best = error
    return best


def locate_camera(poses: list[np.ndarray], size: tuple[int, int]) -> np.ndarray | None:
    """Duruşların ortak kamerası: konum medyanından başlar, medyan artığı azaltan eksen araması."""
    if len(poses) < MIN_POSES:
        return None
    found = [c for c in (camera_position(p, size) for p in poses) if c is not None]
    if not found:
        return None
    camera = np.median(found, axis=0)
    chosen = poses[:: max(len(poses) // SEARCH_POSES, 1)]

    def cost(candidate: np.ndarray) -> float:
        values = [v for v in (pose_residual_m(p, candidate, size) for p in chosen) if v is not None]
        return float(np.median(values)) if values else float("inf")

    best = cost(camera)
    for step in SEARCH_STEPS_M:
        moved = True
        while moved:
            moved = False
            for axis in range(3):
                for sign in (1, -1):
                    trial = camera.copy()
                    trial[axis] += sign * step
                    if trial[2] <= MIN_HEIGHT_M:
                        continue
                    value = cost(trial)
                    if value < best - 1e-3:
                        best, camera, moved = value, trial, True
    return camera


def pose_grid(camera: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """(N,3,3) saha→görüntü duruşları: yuvarlanmasız, kadraj merkezi sahada bir hedefe bakıyor."""
    center = np.array([camera[0], camera[1], -abs(camera[2])])
    width, height = size
    out = []
    for focal in GRID_FOCALS_PX:
        step = max(60.0 * 70.0 / focal, 0.5)
        tx, ty = np.meshgrid(np.arange(*GRID_X_M, step), np.arange(*GRID_Y_M, step))
        forward = np.c_[tx.ravel(), ty.ravel(), np.zeros(tx.size)] - center
        forward /= np.linalg.norm(forward, axis=1, keepdims=True)
        down = np.array([0.0, 0.0, 1.0]) - forward[:, 2:3] * forward
        down /= np.linalg.norm(down, axis=1, keepdims=True)
        right = np.cross(down, forward)
        rotation = np.stack([right, down, forward], axis=1)
        k = np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1.0]])
        g = np.zeros((len(rotation), 3, 3))
        g[:, :, :2] = rotation[:, :, :2]
        g[:, :, 2] = -(rotation @ center)
        out.append(k @ g)
    return np.concatenate(out)


class CameraPriorAnchor:
    """`find_broadcast_anchor` ile aynı imza. `stats` kararların kaynağını sayar."""

    def __init__(self, camera: np.ndarray, size: tuple[int, int]) -> None:
        self._camera = camera
        self._size = size
        self._grid = pose_grid(camera, size)
        self.stats = {"single_frame": 0, "best_pose": 0, "grid": 0, "rejected": 0}

    def __call__(self, mask: np.ndarray, gray: np.ndarray | None = None, tolerance_px: float | None = None) -> BroadcastAnchor:
        result = find_broadcast_anchor(mask, gray, tolerance_px)
        if result.accepted:
            self.stats["single_frame"] += 1
            return result
        if not mask.any():
            self.stats["rejected"] += 1
            return result
        import cv2

        tol = tolerance_px if tolerance_px is not None else DEFAULT_TOLERANCE_PX * self._size[0] / 1280.0
        dist_map = cv2.distanceTransform((~mask.astype(bool)).astype(np.uint8), cv2.DIST_L2, 3)
        lines = [ln for ln in detect_lines(mask) if gray is None or ridge_share(gray, ln) >= RIDGE_MIN_SHARE]
        segments = _segment_mask(lines, mask.shape[:2])
        for source in ("best_pose", "grid"):
            pose = result.best_homography if source == "best_pose" else self._grid_winner(dist_map, segments, tol)
            passed = None if pose is None else self._gate(pose, dist_map, segments, tol)
            if passed is not None:
                self.stats[source] += 1
                return replace(result, homography=pose, accepted=True, note=f"camera_prior_{source}",
                               inlier=passed[0], explained=passed[1])
        self.stats["rejected"] += 1
        return result

    def _gate(self, pose: np.ndarray, dist_map: np.ndarray, segments: np.ndarray, tol: float) -> tuple[float, float] | None:
        residual = pose_residual_m(pose, self._camera, self._size)
        if residual is None or residual > MAX_RESIDUAL_M:
            return None
        _score, inlier, _visible = score_homography(pose, dist_map, pts_m=model_points(1.0), tolerance_px=tol)
        explained = line_coverage(pose, segments, tolerance_px=2.0 * tol)
        return (inlier, explained) if inlier >= MIN_INLIER and explained >= MIN_EXPLAINED else None

    def _grid_winner(self, dist_map: np.ndarray, segments: np.ndarray, tol: float) -> np.ndarray | None:
        hits, visible = score_batch(self._grid, dist_map, model_points(SCORE_STEP_M), COARSE_TOLERANCE_PX)
        key = (hits - (visible - hits)).astype(float)
        key[visible < MIN_VISIBLE_AT_SCORE_STEP] = -np.inf
        picked: list[np.ndarray] = []
        refined: list[tuple[float, np.ndarray]] = []
        for index in np.argsort(-key)[:PICK_LIMIT]:
            if not np.isfinite(key[index]):
                break
            pose = np.linalg.inv(self._grid[index])
            pose = pose / pose[2, 2]
            if not physically_valid(pose, self._size) or any(_distance(pose, other, self._size) < MIN_PICK_DISTANCE_M for other in picked):
                continue
            picked.append(pose)
            fit = refine_homography(pose, dist_map, tolerance_px=tol, step_px=REFINE_STEP_PX)
            final = fit.homography if physically_valid(fit.homography, self._size) else pose
            _score, inlier, _visible = score_homography(final, dist_map, pts_m=model_points(1.0), tolerance_px=tol)
            refined.append((inlier * line_coverage(final, segments, tolerance_px=2.0 * tol), final))
            if len(picked) >= TOP_REFINED:
                break
        return max(refined, key=lambda item: item[0])[1] if refined else None
