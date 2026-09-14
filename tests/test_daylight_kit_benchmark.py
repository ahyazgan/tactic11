"""External match evaluation preserves control isolation, source boxes and abstentions."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict

import pytest

from scripts.soccertrack_v2.benchmark_daylight_kits import (
    benchmark,
    daylight_score,
    load_inputs,
    no_regression,
)
from scripts.soccertrack_v2.prepare_kit_review import select_samples


def payload():
    colors = {"1": [[30, 40, 200]] * 4, "2": [[200, 200, 200]] * 4}
    return {"colors": colors, "alternative_colors": {"local_grass": copy.deepcopy(colors)},
            "samples": [{"frame_idx": 124, "seconds": 4.96,
                         "persons": [[1, 0, 0, 10, 20, .9], [2, 20, 0, 30, 20, .9]]}]}


def test_control_labels_cannot_select_colours_anchors_or_shirt_name_mapping():
    payloads = {s: payload() for s in (0, 3, 6)}
    rows = [{"id": f"{s}-{t}", "segment": s, "track": t, "kit": kit}
            for s in payloads for t, kit in ((1, "blue"), (2, "white"))]
    before = benchmark(payloads, rows)
    flipped = [{**r, "kit": "white" if r["kit"] == "blue" else "blue"} if r["segment"] else r for r in rows]
    after = benchmark(payloads, flipped)
    for method in before:
        assert before[method]["predictions"] == after[method]["predictions"]
        assert before[method]["team_by_track"] == after[method]["team_by_track"]
        assert before[method]["blue_team_from_segment_0"] == after[method]["blue_team_from_segment_0"]
        assert before[method]["mapping_clip"] == after[method]["mapping_clip"]
        assert before[method]["control"]["correct"] == after[method]["control"]["wrong"] == 4


def test_background_detections_are_not_players_and_still_count_as_false_assignments():
    rows = [{"segment": 3, "track": i, "kit": kit}
            for i, kit in enumerate(("blue", "white", "not_person", "other", "uncertain"))]
    predictions = {(3, 0): 0, (3, 1): None, (3, 2): 1, (3, 3): None, (3, 4): 1}
    result = daylight_score(rows, predictions, 0)
    assert result == {"samples": 5, "labeled_players": 2, "correct": 1, "wrong": 0,
                      "unassigned_players": 1, "other_people": 1, "other_assigned": 0,
                      "uncertain": 1, "not_person_detections": 1, "not_person_assigned": 1}
    assert no_regression(result, result)
    assert not no_regression(result, {**result, "correct": 0, "unassigned_players": 2})
    assert not no_regression(result, {**result, "correct": 2, "not_person_assigned": 2})
    assert not no_regression(result, {**result, "samples": 4, "not_person_detections": 0})


@pytest.fixture()
def inputs(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    clips, records, hashes = [], [], {}
    for segment in (0, 3):
        video = tmp_path / f"source_{segment}.mp4"
        video.write_bytes(b"fixture video identity")
        clip = {"segment": segment, "path": str(video), "sha256": hashlib.sha256(video.read_bytes()).hexdigest()}
        clips.append(clip)
        data = {**payload(), "segment": segment, "video": str(video),
                "colour_experiment": {"raw_observations_exactly_reproduced": True, "source_sha256": f"raw-{segment}"}}
        (cache / f"seg_{segment:04d}.json").write_text(json.dumps(data))
        hashes[f"raw/seg_{segment:04d}.json"] = f"raw-{segment}"
        for row in select_samples(data, [5, 20]):
            row["kit"] = "blue" if row["track"] == 1 else "white"
            records.append(row)
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"match": "117093", "clips": clips,
                                  "unavailable_segments": {"6": "fixture", "9": "fixture"}}))
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"records": records, "input_sha256": hashes}))
    return cache, labels, source


def test_source_validation_accepts_only_declared_available_clips(inputs):
    cache, labels, source = inputs
    payloads, rows, provenance = load_inputs(cache, labels, source)
    assert set(payloads) == {0, 3} and len(rows) == 4
    assert provenance["source"]["unavailable_segments"] == {"6": "fixture", "9": "fixture"}


@pytest.mark.parametrize("corruption,message", [
    ("dropped_box", "every fixed-time source box"),
    ("changed_box", "every fixed-time source box"),
    ("changed_cache", "label/cache mismatch"),
    ("changed_video", "source video mismatch"),
    ("undeclared_missing", "missing clips declared"),
    ("unverified_colours", "raw colour observations"),
])
def test_stale_or_cherry_picked_evidence_is_rejected(inputs, corruption, message):
    cache, labels, source = inputs
    annotations = json.loads(labels.read_text())
    manifest = json.loads(source.read_text())
    cache_path = cache / "seg_0000.json"
    data = json.loads(cache_path.read_text())
    if corruption == "dropped_box":
        annotations["records"].pop()
    elif corruption == "changed_box":
        annotations["records"][0]["bbox"][0] += 1
    elif corruption == "changed_cache":
        data["colour_experiment"]["source_sha256"] = "changed"
    elif corruption == "changed_video":
        manifest["clips"][0]["sha256"] = "changed"
    elif corruption == "undeclared_missing":
        del manifest["unavailable_segments"]["9"]
    elif corruption == "unverified_colours":
        data["colour_experiment"]["raw_observations_exactly_reproduced"] = False
    labels.write_text(json.dumps(annotations))
    source.write_text(json.dumps(manifest))
    cache_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        load_inputs(cache, labels, source)


def test_export_keeps_source_time_anonymous_teams_and_rejects_changed_cache(tmp_path):
    from app.tracking.pipeline import PipelineConfig
    from scripts.soccertrack_v2.export_daylight_tracking import export

    data = {**payload(), "segment": 3, "config": asdict(PipelineConfig()),
            "calibration": {"image_size": [100, 100], "points": [
                {"image": [0, 0], "pitch": [0, 0]}, {"image": [100, 0], "pitch": [105, 0]},
                {"image": [100, 100], "pitch": [105, 68]}, {"image": [0, 100], "pitch": [0, 68]}]}}
    data["samples"][0].update(order=0, ball=None)
    cache = tmp_path / "seg_0003.json"
    cache.write_text(json.dumps(data))
    report = {"cache_sha256": {str(cache): hashlib.sha256(cache.read_bytes()).hexdigest()},
              "source": {"clips": [{"segment": 3, "source_start_seconds": 690, "duration_seconds": 30}]},
              "available_control_segments": [3],
              "results": {"raw_rgb_v1": {"team_by_track": {"3": {"1": 0, "2": 1}}},
                          "local_grass_v1": {"team_by_track": {"3": {"1": None, "2": None}}}}}
    result = export(report, tmp_path / "out")
    saved = json.loads((tmp_path / "out" / cache.name).read_text())
    assert result["team_slot_ids_are_anonymous"] and saved["event_accuracy_not_validated"]
    assert result["color_method"] == saved["color_method"] == "raw_rgb_v1"
    assert saved["frames"][0]["minute"] == pytest.approx(round((690 + 4.96) / 60, 4))
    assert {p["team_external_id"] for p in saved["frames"][0]["players"]} == {0, 1}
    cache.write_text("changed")
    with pytest.raises(ValueError, match="measured cache changed"):
        export(report, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
