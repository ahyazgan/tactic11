"""Geometry evidence for duplicate body parts and full-body contact."""
from __future__ import annotations

import numpy as np


def nested_person_mask(boxes: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
    """Suppress a small contained head/leg only when its supporting body exists.

    This is not a maximum-player-count rule or ordinary overlap NMS. Two
    similarly sized bodies survive contact. Parent indices refer to input boxes.
    """
    boxes = np.asarray(boxes, dtype=float).reshape(-1, 4)
    size = np.maximum(boxes[:, 2:] - boxes[:, :2], 0)
    area = size.prod(axis=1)
    valid = np.isfinite(boxes).all(axis=1) & (area > 0)
    parents = {}
    for small in range(len(boxes)):
        if not valid[small]:
            continue
        candidates = []
        for large in range(len(boxes)):
            if (not valid[large] or size[large, 1] < 20
                    or size[small, 1] > size[large, 1] * .55
                    or area[small] > area[large] * .4
                    or size[small, 0] > size[large, 0] * 1.15):
                continue
            intersection = np.maximum(np.minimum(boxes[small, 2:], boxes[large, 2:])
                                      - np.maximum(boxes[small, :2], boxes[large, :2]), 0).prod()
            if intersection / area[small] >= .8:
                candidates.append(large)
        if candidates:
            parents[small] = max(candidates, key=lambda i: area[i])
    # Follow a containment chain to a retained body, never an erased part.
    for small in parents:
        parent = parents[small]
        while parent in parents:
            parent = parents[parent]
        parents[small] = parent
    return np.array([i not in parents for i in range(len(boxes))], dtype=bool), parents


def full_body_contacts(boxes: np.ndarray) -> list[bool]:
    """Comparable full bodies with intersection/minimum-area >= 25%."""
    boxes = np.asarray(boxes, dtype=float).reshape(-1, 4)
    sizes = np.maximum(boxes[:, 2:] - boxes[:, :2], 0)
    areas = sizes.prod(axis=1)
    contact = [False] * len(boxes)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if (min(areas[i], areas[j]) <= 0
                    or min(sizes[i, 1], sizes[j, 1]) < max(sizes[i, 1], sizes[j, 1]) * .55):
                continue
            intersection = np.maximum(np.minimum(boxes[i, 2:], boxes[j, 2:])
                                      - np.maximum(boxes[i, :2], boxes[j, :2]), 0).prod()
            if intersection / max(min(areas[i], areas[j]), 1) >= .25:
                contact[i] = contact[j] = True
    return contact
