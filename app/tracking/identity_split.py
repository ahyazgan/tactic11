"""Confirm appearance discontinuities without joining people or deleting boxes.

The tracker supplies anonymous track IDs. Persistent incompatible kit evidence
starts a new identity segment at the first confirmed observation; it is not a
claim that the preceding or following segment identifies a roster player.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from app.tracking.teams import chromaticity


@dataclass(frozen=True)
class AppearanceBoundary:
    first_index: int
    confirmed_index: int
    phase: int
    prior_color: tuple[float, float, float]
    new_color: tuple[float, float, float]
    source: str = "kit"


@dataclass(frozen=True)
class IdentityObservation:
    continuity_id: int
    track_id: int
    order: int
    seconds: float
    color: np.ndarray | None
    auxiliary_color: np.ndarray | None = None
    collision: bool = False


@dataclass(frozen=True)
class IdentityBoundary:
    continuity_id: int
    raw_track_id: int
    previous_identity: int
    identity: int
    first_order: int
    confirmed_order: int
    first_seconds: float
    confirmed_seconds: float
    source: str


@dataclass(frozen=True)
class IdentitySplitResult:
    observation_ids: tuple[int, ...]
    boundaries: tuple[IdentityBoundary, ...]


def _valid_color(value: np.ndarray | None) -> np.ndarray | None:
    if value is None:
        return None
    color = np.asarray(value, dtype=float)
    if color.shape != (3,) or not np.isfinite(color).all() or np.any(color < 0):
        return None
    return color


def _rgb_tuple(color: np.ndarray) -> tuple[float, float, float]:
    return float(color[0]), float(color[1]), float(color[2])


def appearance_phases(
    colors: Sequence[np.ndarray | None], *, seconds: Sequence[float],
    max_gap_seconds: float, history: int = 32, minimum_history: int = 5,
    consecutive: int = 3, rgb_floor: float = 60.0, tint_floor: float = 15.0,
    spread_factor: float = 2.0,
    auxiliary_colors: Sequence[np.ndarray | None] | None = None,
    collision_mask: Sequence[bool] | None = None,
) -> tuple[list[int], list[AppearanceBoundary]]:
    """Split on confirmed RGB and tint changes, preserving every observation.

    ``max_gap_seconds`` should reflect the caller's sampling cadence. Missing
    colors and longer gaps interrupt confirmation; they never count as evidence.
    Pure brightness changes cannot trigger the primary kit boundary. An optional
    stronger crop cue additionally requires recent full-body overlap and a
    simultaneous change in the broad torso crop.
    """
    if (history < minimum_history or minimum_history < 1 or consecutive < 1
            or not np.isfinite([rgb_floor, tint_floor, spread_factor, max_gap_seconds]).all()
            or min(rgb_floor, tint_floor, spread_factor, max_gap_seconds) <= 0):
        raise ValueError("positive thresholds and sufficient appearance history required")
    if (len(seconds) != len(colors) or not np.isfinite(seconds).all()
            or np.any(np.diff(seconds) < 0)):
        raise ValueError("aligned, finite, ordered observation times required")
    phase = 0
    phases = [0] * len(colors)
    boundaries: list[AppearanceBoundary] = []
    past: deque[np.ndarray] = deque(maxlen=history)
    pending: list[tuple[int, np.ndarray]] = []
    for index, raw_color in enumerate(colors):
        phases[index] = phase
        if index and seconds[index] - seconds[index - 1] > max_gap_seconds:
            pending.clear()
        color = _valid_color(raw_color)
        if color is None:
            pending.clear()
            continue
        incompatible = False
        if len(past) >= minimum_history:
            reference = np.median(past, axis=0)
            rgb_distance = np.linalg.norm(color - reference)
            tint_distance = np.linalg.norm(chromaticity(color) - chromaticity(reference))
            rgb_tolerance = max(rgb_floor, spread_factor * float(np.median(
                np.linalg.norm(np.asarray(past) - reference, axis=1))))
            tint_tolerance = max(tint_floor, spread_factor * float(np.median(
                np.linalg.norm(chromaticity(np.asarray(past)) - chromaticity(reference), axis=1))))
            incompatible = bool(rgb_distance > rgb_tolerance and tint_distance > tint_tolerance)
        if incompatible:
            pending.append((index, color))
            if len(pending) >= consecutive:
                phase += 1
                boundaries.append(AppearanceBoundary(
                    pending[0][0], index, phase, _rgb_tuple(reference),
                    _rgb_tuple(np.median([c for _, c in pending], axis=0)),
                ))
                past.clear()
                for previous_index, evidence in pending:
                    phases[previous_index] = phase
                    past.append(evidence)
                pending.clear()
        else:
            for _, evidence in pending:
                past.append(evidence)
            pending.clear()
            past.append(color)

    if auxiliary_colors is not None:
        if (collision_mask is None or len(auxiliary_colors) != len(colors)
                or len(collision_mask) != len(colors)):
            raise ValueError("aligned auxiliary colors and collision evidence required")
        _, auxiliary_boundaries = appearance_phases(
            auxiliary_colors, seconds=seconds, max_gap_seconds=max_gap_seconds,
            history=history, minimum_history=minimum_history, consecutive=consecutive,
            rgb_floor=rgb_floor, tint_floor=tint_floor, spread_factor=spread_factor,
        )
        first_indices = {boundary.first_index for boundary in boundaries}
        for boundary in auxiliary_boundaries:
            first, confirmed = boundary.first_index, boundary.confirmed_index
            if first in first_indices or first < minimum_history:
                continue
            near_collision = any(
                collision_mask[j] and 0 <= seconds[first] - seconds[j] <= .64
                for j in range(max(0, first - 16), first + 1)
            )
            if not near_collision:
                continue
            before = [_valid_color(c) for c in colors[max(0, first - history):first]]
            after = [_valid_color(c) for c in colors[first:confirmed + 1]]
            valid_before = [c for c in before if c is not None]
            if len(valid_before) < minimum_history or any(c is None for c in after):
                continue
            valid_after = [c for c in after if c is not None]
            prior, current = np.median(valid_before, axis=0), np.median(valid_after, axis=0)
            rgb_distance = np.linalg.norm(current - prior)
            tint_distance = np.linalg.norm(chromaticity(current) - chromaticity(prior))
            if rgb_distance > 40 and tint_distance > 10:
                boundaries.append(replace(boundary, source="collision_appearance"))
                first_indices.add(first)
        boundaries.sort(key=lambda boundary: boundary.first_index)
        phases = [0] * len(colors)
        for phase, boundary in enumerate(boundaries, start=1):
            boundaries[phase - 1] = replace(boundary, phase=phase)
            stop = boundaries[phase].first_index if phase < len(boundaries) else len(colors)
            phases[boundary.first_index:stop] = [phase] * (stop - boundary.first_index)
    return phases, boundaries


def split_identities(
    observations: Sequence[IdentityObservation], *, max_gap_seconds: float,
) -> IdentitySplitResult:
    """Return IDs aligned with ordered input rows; isolate camera epochs.

    The caller retains bounding boxes, confidence, time and all other evidence.
    Every (continuity, order, raw track) key must be unique. Separate camera
    epochs never share an output identity even when the tracker restarts at 1.
    """
    grouped: dict[tuple[int, int], list[tuple[int, IdentityObservation]]] = defaultdict(list)
    seen = set()
    for index, observation in enumerate(observations):
        key = (observation.continuity_id, observation.order, observation.track_id)
        if key in seen:
            raise ValueError("duplicate identity observation")
        seen.add(key)
        group = grouped[observation.continuity_id, observation.track_id]
        if group and (observation.order <= group[-1][1].order
                      or observation.seconds <= group[-1][1].seconds):
            raise ValueError("each track requires strictly ordered observations")
        group.append((index, observation))
    next_id = max((observation.track_id for observation in observations), default=0) + 1
    used: set[int] = set()
    ids = [0] * len(observations)
    audit = []
    for (continuity_id, raw_track_id), group in grouped.items():
        current_id = raw_track_id
        if current_id in used:
            current_id = next_id
            next_id += 1
        used.add(current_id)
        rows = [observation for _, observation in group]
        auxiliary = [row.auxiliary_color for row in rows]
        phases, boundaries = appearance_phases(
            [row.color for row in rows], seconds=[row.seconds for row in rows],
            max_gap_seconds=max_gap_seconds,
            auxiliary_colors=auxiliary if any(c is not None for c in auxiliary) else None,
            collision_mask=[row.collision for row in rows],
        )
        identity_by_phase = {0: current_id}
        for boundary in boundaries:
            previous = current_id
            current_id = next_id
            next_id += 1
            used.add(current_id)
            identity_by_phase[boundary.phase] = current_id
            first, confirmed = rows[boundary.first_index], rows[boundary.confirmed_index]
            audit.append(IdentityBoundary(
                continuity_id, raw_track_id, previous, current_id,
                first.order, confirmed.order, first.seconds, confirmed.seconds,
                boundary.source,
            ))
        for phase, (index, _) in zip(phases, group, strict=True):
            ids[index] = identity_by_phase[phase]
    return IdentitySplitResult(tuple(ids), tuple(audit))
