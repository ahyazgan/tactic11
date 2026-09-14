"""Research-only ball-colour preference; never invent a missing detection.

The default 'any' reproduces confidence-only selection. A known yellow ball
can prefer yellow candidates; when colour evidence is absent, confidence wins.
This is a preference, not proof that the chosen object is the ball.
"""
from __future__ import annotations

import numpy as np

YELLOW_MIN_FRACTION = 0.10


def yellow_fraction(rgb: np.ndarray, box) -> float:
    h, w = rgb.shape[:2]
    x1, y1, x2, y2 = box
    crop = rgb[max(0, min(h, int(y1))):max(0, min(h, int(np.ceil(y2)))),
               max(0, min(w, int(x1))):max(0, min(w, int(np.ceil(x2))))]
    if not crop.size:
        return 0.0
    r, g, b = np.moveaxis(crop.astype(float), -1, 0)
    return float(((np.minimum(r, g) >= 140) & (b < .75 * np.minimum(r, g))
                  & (r < 1.5 * g) & (g < 1.5 * r)).mean())


def preferred_index(confidence, yellow_scores=None) -> int | None:
    values = np.asarray(confidence, dtype=float)
    if not len(values):
        return None
    eligible = np.arange(len(values))
    if yellow_scores is not None:
        scores = np.asarray(yellow_scores, dtype=float)
        if scores.shape != values.shape:
            raise ValueError("one colour score required per ball candidate")
        preferred = np.flatnonzero(scores >= YELLOW_MIN_FRACTION)
        if len(preferred):
            eligible = preferred
    return int(eligible[np.argmax(values[eligible])])


def select_ball_index(rgb: np.ndarray, boxes, confidence, appearance: str = "any") -> int | None:
    if appearance not in {"any", "yellow"}:
        raise ValueError(f"unsupported ball appearance: {appearance}")
    scores = [yellow_fraction(rgb, box) for box in boxes] if appearance == "yellow" else None
    return preferred_index(confidence, scores)
