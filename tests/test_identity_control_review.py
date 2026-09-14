"""Control review selection must not depend on tracker predictions."""
from __future__ import annotations

import json

import pytest

from scripts.soccertrack_v2.prepare_identity_control import (
    START_FRAMES,
    context_frames,
    review_manifests,
    select_raw_frames,
)


def source():
    frames = sorted({frame for start in START_FRAMES for frame in context_frames(start)})
    return {"segment": 40,
            "samples": [{"order": index, "frame_idx": frame,
                         "persons": [[999, 999, 999, 999, 999, .99]],
                         "person_teams": {"999": 1}}
                        for index, frame in enumerate(frames)],
            "detected_persons": {str(index): [
                {"box": [10., 20., 20., 40.], "confidence": .1, "color": [1, 2, 3]},
                {"box": [30., 20., 40., 40.], "confidence": .9, "color": [4, 5, 6]},
            ] for index in range(len(frames))}}


def test_all_raw_boxes_survive_blinded_selection_in_original_order():
    selected = select_raw_frames(source(), 40)
    records, observations, pairs = review_manifests(selected, "source.mp4")
    assert len(records) == 4 and len(observations) == 8 and len(pairs) == 4
    assert records[0]["id"] == "40-374-d0"
    assert records[1]["bbox"] == [30., 20., 40., 40.]
    assert all(record["kit"] is None for record in records)
    assert all(pair["right"] is None and pair["relation"] is None for pair in pairs)
    assert pairs[0]["endpoint_candidates"] == ["40-404-d0", "40-404-d1"]
    serialized = json.dumps([records, observations, pairs])
    assert "999" not in serialized and "confidence" not in serialized and "color" not in serialized
    assert "team" not in serialized and "track" not in serialized


def test_exact_frames_required_without_nearest_frame_fallback():
    payload = source()
    payload["samples"] = [row for row in payload["samples"] if row["frame_idx"] != 374]
    with pytest.raises(ValueError, match="exact source frames missing"):
        select_raw_frames(payload, 40)


def test_duplicate_frames_mismatched_segment_and_invalid_boxes_fail():
    payload = source()
    payload["samples"].append(dict(payload["samples"][0]))
    with pytest.raises(ValueError, match="duplicate source frame"):
        select_raw_frames(payload, 40)
    with pytest.raises(ValueError, match="segment disagrees"):
        select_raw_frames(source(), 50)
    payload = source()
    payload["detected_persons"]["0"][0]["box"] = [0, 0, float("nan"), 1]
    with pytest.raises(ValueError, match="invalid detector box"):
        select_raw_frames(payload, 40)


def test_temporal_context_is_fixed_and_contains_exact_start_end():
    for start in START_FRAMES:
        frames = context_frames(start)
        assert frames == sorted(set(frames))
        assert min(frames) == start - 8 and max(frames) == start + 38
        assert start in frames and start + 30 in frames
        assert all(start - 8 <= frame <= start + 38 for frame in frames)
