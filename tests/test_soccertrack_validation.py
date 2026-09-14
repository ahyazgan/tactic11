"""Validation must not count duplicate detections/events as additional ground truth."""
import json

import numpy as np
import pytest

from scripts.soccertrack_v2.evaluate_events import temporal_matches
from scripts.soccertrack_v2.evaluate_teams import matched
from scripts.soccertrack_v2.export_gt import annotations


def test_gt_stream_reads_nested_objects_and_empty_array(tmp_path) -> None:
    path = tmp_path / "gt.json"
    objects = [{"image_id": "3000001", "bbox": {"x": 1}, "note": "[,]"}]
    path.write_text(json.dumps({"images": [], "annotations": objects}), encoding="utf-8")
    assert list(annotations(path)) == objects
    path.write_text('{"annotations": []}', encoding="utf-8")
    assert list(annotations(path)) == []
    path.write_text('{"annotations": [{"image_id":', encoding="utf-8")
    with pytest.raises(ValueError, match="truncated"):
        list(annotations(path))


def test_spatial_match_is_one_to_one_and_respects_radius() -> None:
    gt = np.zeros((2, 10))
    gt[:, 6:8] = [[0, 0], [10, 0]]
    pts = np.array([[52.5, 34], [52.6, 34], [62.5, 34], [90, 60]])
    pairs = matched(pts, gt, 3)
    assert len(pairs) == 2
    assert len({j for _, j in pairs}) == 2
    assert all(i != 3 for i, _ in pairs)


def test_event_match_cannot_double_count_one_gt_event() -> None:
    assert temporal_matches([10.0, 10.1, 20], [10], 1) == 1
    assert temporal_matches([], [10], 1) == 0
    assert temporal_matches([10, 20], [12, 22], 1) == 0
    assert temporal_matches([10, 20], [12, 22], 2) == 2
