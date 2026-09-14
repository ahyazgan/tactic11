"""Development-only suppression of strongly contained head/leg detections.

No count cap: overlapping full bodies remain separate. Labels must distinguish
removed duplicate parts from missing independent people before promotion.
"""
from __future__ import annotations

import numpy as np


def nested_keep(boxes: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
    boxes = np.asarray(boxes, dtype=float).reshape(-1, 4)
    size = np.maximum(boxes[:, 2:] - boxes[:, :2], 0)
    area = size.prod(axis=1)
    parents = {}
    for small in range(len(boxes)):
        if area[small] <= 0:
            continue
        candidates = []
        for large in range(len(boxes)):
            if (size[large, 1] < 20 or size[small, 1] > size[large, 1] * .55
                    or area[small] > area[large] * .4
                    or size[small, 0] > size[large, 0] * 1.15):
                continue
            intersection = np.maximum(np.minimum(boxes[small, 2:], boxes[large, 2:])
                                      - np.maximum(boxes[small, :2], boxes[large, :2]), 0).prod()
            if intersection / area[small] >= .8:
                candidates.append(large)
        if candidates:
            # A part cannot erase its supporting body; choose the biggest body
            # when the part lies inside multiple candidates.
            parents[small] = max(candidates, key=lambda i: area[i])
    return np.array([i not in parents for i in range(len(boxes))]), parents
