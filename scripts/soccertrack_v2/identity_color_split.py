"""Pure experimental helper for confirmed appearance identity boundaries.

Call separately for each raw track within one camera-continuity epoch. Returned
phase numbers are local; callers allocate globally unique output identities and
retain the original observation boxes. This deliberately never joins players.
"""
from __future__ import annotations

from collections import deque
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


def appearance_phases(
    colors: Sequence[np.ndarray | None], *, history: int = 32,
    minimum_history: int = 5, consecutive: int = 3,
    rgb_floor: float = 60.0, tint_floor: float = 15.0,
    spread_factor: float = 2.0,
    auxiliary_colors: Sequence[np.ndarray | None] | None = None,
    collision_mask: Sequence[bool] | None = None,
    seconds: Sequence[float] | None = None,
) -> tuple[list[int], list[AppearanceBoundary]]:
    """Confirm incompatible RGB *and* tint; backdate to first conflicting color.

    A common brightness multiplier alone never splits an identity. Unconfirmed
    deviations return to the history when a compatible observation arrives.
    Missing/invalid colors cannot serve as appearance evidence. Confirmation is
    counted in available color observations, not elapsed video frames.
    """
    if (history < minimum_history or minimum_history < 1 or consecutive < 1
            or not np.isfinite([rgb_floor, tint_floor, spread_factor]).all()
            or min(rgb_floor, tint_floor, spread_factor) <= 0):
        raise ValueError("positive appearance thresholds and sufficient history required")
    phase = 0
    phases = [0] * len(colors)
    boundaries = []
    past: deque[np.ndarray] = deque(maxlen=history)
    pending: list[tuple[int, np.ndarray]] = []
    for index, raw_color in enumerate(colors):
        phases[index] = phase
        if raw_color is None:
            continue
        color = np.asarray(raw_color, dtype=float)
        if color.shape != (3,) or not np.isfinite(color).all() or np.any(color < 0):
            continue
        incompatible = False
        if len(past) >= minimum_history:
            reference = np.median(past, axis=0)
            rgb_distance = np.linalg.norm(color - reference)
            tint_distance = np.linalg.norm(chromaticity(color) - chromaticity(reference))
            rgb_tolerance = max(rgb_floor, spread_factor * float(np.median(
                np.linalg.norm(np.asarray(past) - reference, axis=1))))
            tint_tolerance = max(tint_floor, spread_factor * float(np.median(
                np.linalg.norm(chromaticity(past) - chromaticity(reference), axis=1))))
            incompatible = rgb_distance > rgb_tolerance and tint_distance > tint_tolerance
        if incompatible:
            pending.append((index, color))
            if len(pending) >= consecutive:
                phase += 1
                boundaries.append(AppearanceBoundary(
                    pending[0][0], index, phase,
                    tuple(map(float, reference)),
                    tuple(map(float, np.median([c for _, c in pending], axis=0))),
                ))
                past.clear()
                # Include missing-color observations within the confirmed
                # transition interval in the new identity, without using them
                # as evidence. No later earlier-phase rows remain interleaved.
                phases[pending[0][0]:index + 1] = [phase] * (index - pending[0][0] + 1)
                for _, evidence in pending:
                    past.append(evidence)
                pending.clear()
        else:
            for _, evidence in pending:
                past.append(evidence)
            pending.clear()
            past.append(color)
    if auxiliary_colors is not None:
        if (collision_mask is None or seconds is None
                or len(auxiliary_colors) != len(colors)
                or len(collision_mask) != len(colors) or len(seconds) != len(colors)
                or not np.isfinite(seconds).all()
                or np.any(np.diff(seconds) < 0)):
            raise ValueError("aligned collision evidence and ordered times required")
        _, auxiliary_boundaries = appearance_phases(
            auxiliary_colors, history=history, minimum_history=minimum_history,
            consecutive=consecutive, rgb_floor=rgb_floor, tint_floor=tint_floor,
            spread_factor=spread_factor,
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

            def valid_values(values):
                return [np.asarray(value, dtype=float) for value in values
                        if value is not None and np.asarray(value).shape == (3,)
                        and np.isfinite(value).all() and not np.any(np.asarray(value) < 0)]

            before = valid_values(colors[max(0, first - history):first])
            after = valid_values(colors[first:confirmed + 1])
            if len(before) < minimum_history or not after:
                continue
            prior, current = np.median(before, axis=0), np.median(after, axis=0)
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
