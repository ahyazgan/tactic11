"""Reject perimeter tracks without evidence inside an annotated playing field.

A player may stand still or briefly step over a touchline. Retain the entire
track once two observations support it on the field. This is a clip-level
geometry filter, not a person classifier or a player-identity guarantee.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.tracking.calibration import PitchCalibration
    from app.tracking.pipeline import SampledObservation

MIN_FIELD_OBSERVATIONS = 2
BOUNDARY_TOLERANCE_HEIGHT = 0.002


@lru_cache(maxsize=32)
def _boundary(points: tuple, length: float, width: float, method: str) -> np.ndarray | None:
    """Require all four corners and curved-edge samples for TPS cameras."""
    if not points or not np.isfinite(np.asarray(points)).all():
        return None
    for corner in ((0, 0), (length, 0), (length, width), (0, width)):
        if not any(np.allclose(p[2:], corner, atol=1e-6, rtol=0) for p in points):
            return None
    edges = [([p for p in points if abs(p[3]) < 1e-6], 2, False),
             ([p for p in points if abs(p[2] - length) < 1e-6], 3, False),
             ([p for p in points if abs(p[3] - width) < 1e-6], 2, True),
             ([p for p in points if abs(p[2]) < 1e-6], 3, True)]
    result: list[tuple[float, float]] = []
    for edge, axis, reverse in edges:
        if len({p[axis] for p in edge}) < (3 if method == "tps" else 2):
            return None
        for p in sorted(edge, key=lambda p: p[axis], reverse=reverse):
            if not result or result[-1] != p[:2]:
                result.append(p[:2])
    if result[-1] == result[0]:
        result.pop()
    poly = np.asarray(result, dtype=float)
    if len(poly) < 4 or len(set(result)) != len(result):
        return None
    # Reject crossing edges instead of trusting an invalid annotated perimeter.
    def cross(a, b, c):
        d, e = b - a, c - a
        return d[0] * e[1] - d[1] * e[0]
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        for j in range(i + 2, len(poly)):
            if i == 0 and j == len(poly) - 1:
                continue
            c, d = poly[j], poly[(j + 1) % len(poly)]
            if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
                return None
    area = abs(np.sum(poly[:, 0] * np.roll(poly[:, 1], 1) - poly[:, 1] * np.roll(poly[:, 0], 1))) / 2
    if area < 1:
        return None
    poly.setflags(write=False)
    return poly


def annotated_boundary(calibration: PitchCalibration) -> np.ndarray | None:
    if not getattr(calibration, "points", ()):
        return None
    points = tuple((*p.image, *p.pitch) for p in calibration.points)
    return _boundary(points, calibration.pitch_length_m, calibration.pitch_width_m, calibration.method)


def inside_boundary(points: np.ndarray, polygon: np.ndarray, tolerance_px: float) -> np.ndarray:
    """Ray casting plus distance to edges; boundary points count as inside."""
    q = np.asarray(points, dtype=float).reshape(-1, 2)
    finite = np.isfinite(q).all(axis=1)
    q = np.where(finite[:, None], q, 0.)
    a, b = polygon, np.roll(polygon, -1, axis=0)
    edge = b - a
    delta = q[:, None, :] - a
    length2 = np.sum(edge * edge, axis=1)
    t = np.clip(np.sum(delta * edge, axis=2) / np.maximum(length2, 1e-12), 0, 1)
    distance2 = np.sum((delta - t[:, :, None] * edge) ** 2, axis=2)
    near = np.min(distance2, axis=1) <= tolerance_px ** 2
    y = q[:, 1:2]
    crosses_y = (a[:, 1] > y) != (b[:, 1] > y)
    dy = b[:, 1] - a[:, 1]
    safe_dy = np.where(dy == 0, 1., dy)
    x_intersection = a[:, 0] + (y - a[:, 1]) * edge[:, 0] / safe_dy
    inside = np.sum(crosses_y & (q[:, :1] < x_intersection), axis=1) % 2 == 1
    return finite & (near | inside)


def filter_person_tracks(samples: list[SampledObservation], calibration: PitchCalibration | None,
                         *, enabled: bool = True) -> dict:
    """Filter in place before team fitting; preserve accepted boxes and IDs."""
    reason = ("disabled" if not enabled else "no_static_calibration" if calibration is None else
              "changing_calibration" if any(s.calibration is not None for s in samples) else None)
    polygon = annotated_boundary(calibration) if reason is None and calibration is not None else None
    if reason is None and polygon is None:
        reason = "incomplete_or_invalid_annotated_boundary"
    before = sum(len(s.persons) for s in samples)
    stats = {"method": "annotated_perimeter_track_v1", "applied": reason is None,
             "skip_reason": reason, "observations_before": before, "observations_removed": 0,
             "tracks_removed": 0, "min_field_observations": MIN_FIELD_OBSERVATIONS}
    if reason is not None:
        return stats
    assert calibration is not None and polygon is not None
    tolerance = max(1., calibration.image_size[1] * BOUNDARY_TOLERANCE_HEIGHT)
    keys = [(s.continuity_id, p[0]) for s in samples for p in s.persons]
    feet = np.array([((p[1] + p[3]) / 2, p[4]) for s in samples for p in s.persons]).reshape(-1, 2)
    support = Counter(key for key, inside in zip(keys, inside_boundary(feet, polygon, tolerance), strict=True) if inside)
    rejected = {key for key in keys if support[key] < MIN_FIELD_OBSERVATIONS}
    for sample in samples:
        sample.persons = [p for p in sample.persons if (sample.continuity_id, p[0]) not in rejected]
    stats.update(tolerance_px=tolerance, tracks_removed=len(rejected),
                 observations_removed=before - sum(len(s.persons) for s in samples),
                 rejected_tracks=[{"continuity_id": c, "track_id": t} for c,t in sorted(rejected)])
    return stats
