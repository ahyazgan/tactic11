"""Sabit kamera bekçisi: üretilmiş yayın duruşunu, maçın ana kamerasıyla açıklanabiliyor mu diye sınar.

Üretime bağlı değildir. Ön kayıt: docs/measurements/broadcast-tracking-round3-preregistration.json.

Ana kamera sabit bir noktada döner ve zoom yapar. Maçın kamera konumu duruşlardan bulunur; bir duruş
bu konumdan yalnız dönme+zoom ile açıklanamıyorsa yanlış çizgiye oturmuş ya da başka kameradandır.
Takibi, çapayı ve çizgi kapısını etkilemez, yalnız üretilmiş duruşu reddeder.
"""
from __future__ import annotations

import numpy as np

REJECT_ABOVE_M = 2.0
MIN_POSES = 10
SEARCH_POSES = 40
SEARCH_STEPS_M = (8.0, 4.0, 2.0, 1.0, 0.5)
MIN_HEIGHT_M = 5.0
FOCALS_PX = np.geomspace(800, 16000, 90)


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
    for focal in FOCALS_PX:
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


def guard_poses(poses: list[np.ndarray], size: tuple[int, int]) -> list[bool]:
    """Her duruş için tutulsun mu. Kamera bulunamayacak kadar az duruşta hepsi reddedilir."""
    if len(poses) < MIN_POSES:
        return [False] * len(poses)
    camera = locate_camera(poses, size)
    if camera is None:
        return [False] * len(poses)
    residuals = (pose_residual_m(p, camera, size) for p in poses)
    return [r is not None and r <= REJECT_ABOVE_M for r in residuals]
