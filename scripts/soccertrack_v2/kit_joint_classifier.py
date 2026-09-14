"""Development-only dual-fraction shirt classifier; no production defaults change.

Bright pixels supply the team palette. The broader shirt crop independently
retains evidence of another colour, such as an official's shirt. Both palettes
are learned without kit labels; segment-zero labels only name anonymous slots.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from app.tracking.teams import (
    CHROMATICITY_MIN_DISTANCE,
    TeamAssigner,
    TeamAssignment,
    chromaticity,
    distinct_team_colors,
)


def fit_dual_fraction(
    bright_observations: Mapping[int, Sequence],
    broad_observations: Mapping[int, Sequence],
    anchor_colors: np.ndarray | None = None,
    *,
    eligible_tracks: set[int] | None = None,
) -> TeamAssignment:
    """Fit bright20% RGB; veto differently coloured broad40% track medians.

    A broad RGB-distance veto is deliberately absent: illumination can move
    an otherwise valid shirt far from its broad-crop RGB centre. The existing
    brightness-independent tint threshold applies to that second observation.
    """
    bright, broad = TeamAssigner(), TeamAssigner()
    for track, observations in bright_observations.items():
        for color in observations:
            bright.observe(track, np.asarray(color, dtype=float))
    for track, observations in broad_observations.items():
        for color in observations:
            broad.observe(track, np.asarray(color, dtype=float))
    assignment = bright.fit(anchor_colors, eligible_tracks=eligible_tracks)
    broad_assignment = broad.fit(eligible_tracks=eligible_tracks)
    tracks = [track for track, observations in broad_observations.items()
              if len(observations) >= 2 and (eligible_tracks is None or track in eligible_tracks)]
    if len(tracks) < 2 or not distinct_team_colors(broad_assignment.centers):
        return TeamAssignment({track: None for track in bright_observations}, np.zeros((2, 3)),
                              frozenset(bright_observations), "broader shirt colour evidence is ambiguous")
    features = np.array([np.median(np.asarray(broad_observations[track]), axis=0) for track in tracks])
    centers = broad_assignment.centers
    nearest = np.linalg.norm(features[:, None] - centers, axis=-1).argmin(axis=1)
    tint_distance = np.linalg.norm(chromaticity(features) - chromaticity(centers)[nearest], axis=-1)
    thresholds = {cluster: max(float(np.median(tint_distance[nearest == cluster])) * 2.5,
                               CHROMATICITY_MIN_DISTANCE)
                  for cluster in range(2) if np.any(nearest == cluster)}
    rejected = {track for i, track in enumerate(tracks)
                if tint_distance[i] > thresholds[int(nearest[i])]}
    # Missing a second feature is uncertainty, not evidence of a kit colour.
    rejected.update(set(bright_observations) - set(tracks))
    teams = {track: None if track in rejected else team for track, team in assignment.team_by_track.items()}
    return TeamAssignment(teams, assignment.centers,
                          frozenset(set(assignment.outlier_tracks) | rejected), assignment.note)
