"""Independent shirt colour evidence for team assignment and identity continuity.

The brightest torso pixels retain a useful team colour in small, dark crops.
A broader view independently rejects another shirt colour that a bright number
or skin patch could hide. Saturated fabric is an additional continuity cue; it
does not replace the team palette, because that regresses night-time footage.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np

from app.tracking.teams import (
    CHROMATICITY_MIN_DISTANCE,
    TeamAssigner,
    TeamAssignment,
    chromaticity,
    distinct_team_colors,
)

ColorObservation: TypeAlias = np.ndarray | Sequence[float] | None
ColorHistories: TypeAlias = Mapping[int, Sequence[ColorObservation]]


@dataclass(frozen=True, slots=True)
class KitEvidence:
    """Three raw RGB summaries of the same detected torso, without kit labels."""

    bright: np.ndarray
    broad: np.ndarray
    appearance: np.ndarray


def extract_kit_evidence(frame_rgb: np.ndarray, box: Sequence[float]) -> KitEvidence | None:
    """Share the crop and brightness sort for the frozen 20%/40%/fabric features.

    Coordinates, grass exclusion, rounding and minimum pixel counts match
    ``torso_color``. No lighting adjustment or colour-specific kit rule is used.
    ``None`` means the source box supplies no usable torso pixels.
    """
    coordinates = np.asarray(box, dtype=float)
    if coordinates.shape != (4,) or not np.isfinite(coordinates).all():
        return None
    if frame_rgb.ndim != 3 or frame_rgb.shape[2] != 3:
        return None
    x1, y1, x2, y2 = map(round, coordinates)
    height, width = frame_rgb.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
    bw, bh = x2 - x1, y2 - y1
    if bw < 2 or bh < 4:
        return None
    pixels = frame_rgb[
        y1 + int(bh * .1):y1 + int(bh * .55),
        x1 + int(bw * .2):x1 + int(bw * .8),
    ].reshape(-1, 3).astype(float)
    if not len(pixels) or not np.isfinite(pixels).all():
        return None
    r, g, b = pixels.T
    kept = pixels[~((g > 1.12 * r) & (g > 1.12 * b))]
    if len(kept) < max(4, len(pixels) * .12):
        kept = pixels
    ordered = kept[np.argsort(kept.max(axis=1))]
    bright = ordered[-max(4, int(len(ordered) * .2)):].mean(axis=0)
    broad = ordered[-max(4, int(len(ordered) * .4)):].mean(axis=0)
    # Excluding the darker half avoids saturation magnifying near-black noise.
    candidates = ordered[len(ordered) // 2:]
    value = candidates.max(axis=1)
    saturation = (value - candidates.min(axis=1)) / np.maximum(value, 1.)
    fabric = candidates[np.argsort(saturation)[-max(4, len(candidates) // 2):]]
    return KitEvidence(bright, broad, fabric.mean(axis=0))


def _valid_histories(histories: ColorHistories) -> dict[int, list[np.ndarray]]:
    result = {}
    for track, observations in histories.items():
        valid = []
        for color in observations:
            if color is None:
                continue
            value = np.asarray(color, dtype=float)
            if value.shape == (3,) and np.isfinite(value).all():
                valid.append(value)
        result[track] = valid
    return result


def fit_kit_evidence(
    bright_observations: ColorHistories,
    broad_observations: ColorHistories,
    anchor_colors: np.ndarray | None = None,
    *,
    eligible_tracks: set[int] | None = None,
) -> TeamAssignment:
    """Fit bright20% RGB and retain broad40% evidence of another shirt colour.

    Histories belong to coherent tracklets, before identity-fragment linking.
    An identity link must preserve these assignments and their palette; fitting
    again on merged histories would change the influence of each observation.
    Broad RGB distance is not a veto: valid shirts change brightness in shadow.
    """
    bright_colors = _valid_histories(bright_observations)
    broad_colors = _valid_histories(broad_observations)
    bright, broad = TeamAssigner(), TeamAssigner()
    for track, observations in bright_colors.items():
        for color in observations:
            bright.observe(track, color)
    for track, observations in broad_colors.items():
        for color in observations:
            broad.observe(track, color)
    assignment = bright.fit(anchor_colors, eligible_tracks=eligible_tracks)
    broad_assignment = broad.fit(eligible_tracks=eligible_tracks)
    tracks = [track for track, observations in broad_colors.items()
              if len(observations) >= 2 and (eligible_tracks is None or track in eligible_tracks)]
    if len(tracks) < 2 or not distinct_team_colors(broad_assignment.centers):
        return TeamAssignment({track: None for track in bright_colors}, np.zeros((2, 3)),
                              frozenset(bright_colors), "forma renginin ikinci gözlemi belirsiz")
    features = np.array([np.median(np.asarray(broad_colors[track]), axis=0) for track in tracks])
    centers = broad_assignment.centers
    nearest = np.linalg.norm(features[:, None] - centers, axis=-1).argmin(axis=1)
    tint_distance = np.linalg.norm(chromaticity(features) - chromaticity(centers)[nearest], axis=-1)
    thresholds = {cluster: max(float(np.median(tint_distance[nearest == cluster])) * 2.5,
                               CHROMATICITY_MIN_DISTANCE)
                  for cluster in range(2) if np.any(nearest == cluster)}
    rejected = {track for i, track in enumerate(tracks)
                if tint_distance[i] > thresholds[int(nearest[i])]}
    rejected.update(set(bright_colors) - set(tracks))
    teams = {track: None if track in rejected else assignment.team_by_track.get(track)
             for track in bright_colors}
    outliers = frozenset(track for track, team in teams.items() if team is None)
    return TeamAssignment(teams, assignment.centers, outliers, assignment.note)
