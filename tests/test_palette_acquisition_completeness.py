"""Reject decoder truncation even when the raw cache was written successfully."""
import json
from copy import deepcopy

import pytest

from scripts.soccertrack_v2.validate_palette_acquisition import (
    digest,
    validate_group,
    validate_payload,
)


@pytest.fixture
def acquisition():
    spec = {"config": {"track_fps": 15}, "calibration": {"image_size": [3840, 1906]}}
    payload = {"segment": 78, **deepcopy(spec),
               "samples": [{"order": i, "frame_idx": 2 * i, "seconds": 2 * i / 25} for i in range(375)],
               "detected_persons": {str(i): [] for i in range(375)}}
    return payload, spec


def test_complete_empty_detection_frames_are_valid(acquisition):
    payload, spec = acquisition
    assert validate_payload(payload, spec, 78) == 375


@pytest.mark.parametrize("count", [0, 1, 250, 374])
def test_truncated_decoder_output_is_not_a_successful_capture(acquisition, count):
    payload, spec = acquisition
    payload["samples"] = payload["samples"][:count]
    with pytest.raises(ValueError, match="Incomplete capture"):
        validate_payload(payload, spec, 78)


@pytest.mark.parametrize("fault, message", [
    ("frame", "source frame"), ("order", "sample order"),
    ("seconds", "timestamp"), ("missing_detections", "detection frames"),
    ("extra_detections", "detection frames"), ("config", "configuration"),
])
def test_complete_count_does_not_hide_gaps_or_repeated_frames(acquisition, fault, message):
    payload, spec = acquisition
    if fault == "frame":
        payload["samples"][200]["frame_idx"] = 398
    elif fault == "order":
        payload["samples"][200]["order"] = 199
    elif fault == "seconds":
        payload["samples"][200]["seconds"] = float("nan")
    elif fault == "missing_detections":
        del payload["detected_persons"]["200"]
    elif fault == "extra_detections":
        payload["detected_persons"]["375"] = []
    elif fault == "config":
        payload["config"]["track_fps"] = 5
    with pytest.raises(ValueError, match=message):
        validate_payload(payload, spec, 78)


def test_missing_completion_manifest_is_rejected(tmp_path):
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"groups": {"night": {}}}))
    with pytest.raises(ValueError, match="manifest missing"):
        validate_group("night", root=tmp_path, freeze=freeze)


@pytest.mark.parametrize("fault", [None, "changed_video", "changed_cache", "short_cache_with_valid_hash", "changed_interval"])
def test_manifest_validation_links_complete_cache_to_original_extraction(tmp_path, acquisition, fault):
    payload, spec = acquisition
    spec["segments"] = {"78": 2340}
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"groups": {"night": spec}}))
    raw = tmp_path / "night" / "raw"
    source = tmp_path / "night" / "source"
    raw.mkdir(parents=True)
    source.mkdir()
    video = source / "seg_0078.mp4"
    video.write_bytes(b"synthetic-source-for-hash-validation")
    payload["video"] = str(video)
    if fault == "short_cache_with_valid_hash":
        payload["samples"] = []
    cache = raw / "seg_0078.json"
    cache.write_text(json.dumps(payload))
    (source / "manifest.json").write_text(json.dumps({
        "freeze_sha256": digest(freeze), "clips": [{"segment": 78, "frames": 750,
        "start_seconds": 2341 if fault == "changed_interval" else 2340, "sha256": digest(video)}],
    }))
    (raw / "manifest.json").write_text(json.dumps({
        "freeze_sha256": digest(freeze), "video_sha256": {str(video): digest(video)},
        "output_sha256": {str(cache): digest(cache)},
    }))
    if fault == "changed_video":
        video.write_bytes(b"different-source")
    elif fault == "changed_cache":
        cache.write_text("{}")
    if fault:
        with pytest.raises(ValueError):
            validate_group("night", root=tmp_path, freeze=freeze)
    else:
        assert validate_group("night", root=tmp_path, freeze=freeze)["samples"] == {"78": 375}
