"""Validate persisted anonymous team palettes without fitting on later clips."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.tracking.teams import distinct_team_colors


def team_anchor(value: Any) -> np.ndarray | None:
    """Return a usable two-team RGB palette, or no anchor for uncertain input."""
    try:
        colors = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if (not distinct_team_colors(colors) or np.any(colors < 0)
            or np.any(colors > 255)):
        return None
    return colors.copy()
