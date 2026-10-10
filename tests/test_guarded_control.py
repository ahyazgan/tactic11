"""Fail closed on incomplete source acquisition, unsealed labels or altered evidence."""
import json
import platform
from copy import deepcopy

import pytest

from scripts.soccertrack_v2 import guarded_control as control
from scripts.soccertrack_v2.prepare_identity_control import context_frames


def label_fixture():
    frames = sorted({f for start in control.START_FRAMES for f in context_frames(start)})
    raw = dict(segment=68, samples=[dict(order=i, frame_idx=f) for i, f in enumerate(frames)],
        detected_persons={str(i): [dict(box=[10., 10., 20., 40.]), dict(box=[30., 10., 40., 40.])]
                          for i in range(len(frames))})
    observations, starts = control.expected_labels({68: raw})
    rows = [{**r, "kit": "blue" if r["detector_index"] == 0 else "white",
             "box_scope": "single_person", "visual_basis": "Clear synthetic source fixture"}
            for r in observations.values()]
    meta = dict(predictions_visible_during_labeling=False, reviewer="synthetic test", limitations="Not imagery")
    labels = dict(**meta, records=rows, source_review=[dict(id=i, status="same_labeled", reason="Clear source") for i in sorted(starts)])
    pairs = []
    for identity in sorted(starts):
        row = observations[identity]
        for relation, index in (("same", row["detector_index"]), ("different", 1 - row["detector_index"])):
            pairs.append(dict(left=identity, right=f"68-{row['frame_idx'] + 30}-d{index}",
                              relation=relation, visual_basis="Known synthetic identities"))
    return labels, dict(**meta, observations=list(observations.values()), pairs=pairs), {68: raw}


def coverage_fixture():
    sample = dict(order=0, frame_idx=0, seconds=0., continuity_id=0,
                  persons=[[1, 10., 10., 20., 40., .9]], person_teams={"1": 0})
    raw = dict(samples=[deepcopy(sample)], detected_persons={"0": [
        dict(box=[10., 10., 20., 40.], confidence=.9), dict(box=[30., 10., 40., 40.], confidence=.8)]})
    base = dict(samples=[sample])
    candidate = deepcopy(base)
    candidate["samples"][0].update(persons=[[8, 10., 10., 20., 40., .9], [9, 30., 10., 40., 40., .8]],
                                    person_teams={"8": 0, "9": None})
    return raw, base, candidate


def test_control_intervals_fit_and_exclude_consumed_identity_and_speed_controls():
    previous = {"day": [(1800, 1830), (1860, 1890), (1920, 1950), (1980, 2010), (2100, 2110), (2220, 2250)],
                "night": [(2340, 2370), (2400, 2430), (2460, 2490), (2520, 2550), (2580, 2590), (2640, 2670)]}
    for group, count in (("day", 67625), ("night", 67375)):
        starts = list(control.SOURCES[group]["segments"].values())
        control.validate_control_timing(25., count, starts)
        assert all(not (start < right and start + 30 > left) for start in starts for left, right in previous[group])


@pytest.mark.parametrize("existing", ["freeze", "pixels"])
def test_freeze_refuses_prior_decision_or_opened_pixels(tmp_path, monkeypatch, existing):
    monkeypatch.setattr(control, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(control, "ROOT", tmp_path / "pixels")
    if existing == "freeze":
        control.FREEZE.write_text("{}")
    else:
        control.ROOT.mkdir()
    with pytest.raises(ValueError, match="before extraction"):
        control.freeze()


def test_committed_seal_requires_exact_head_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "seal.json"
    path.write_bytes(b'{"sealed":true}\n')
    monkeypatch.setattr(control.subprocess, "check_output", lambda command: path.read_bytes())
    control.committed(path)
    monkeypatch.setattr(control.subprocess, "check_output", lambda command: b'{"sealed":false}\n')
    with pytest.raises(ValueError, match="committed unchanged"):
        control.committed(path)


@pytest.mark.parametrize("changed", ["code", "input", "runtime"])
def test_freeze_verifier_rejects_changes_before_any_pixel_access(tmp_path, monkeypatch, changed):
    code, data, freeze = (tmp_path / name for name in ("code.py", "source.mp4", "freeze.json"))
    code.write_text("value = 1\n")
    data.write_bytes(b"source")
    decision = dict(profile=control.PROFILE, methods=list(control.METHODS), python=platform.python_version(),
        runtime_versions={"torch": "frozen"}, code_sha256_lf={str(code): control.code_hash(code)},
        input_sha256={str(data): control.digest(data)})
    freeze.write_text(json.dumps(decision))
    monkeypatch.setattr(control, "FREEZE", freeze)
    monkeypatch.setattr(control, "version", lambda _: "changed" if changed == "runtime" else "frozen")
    if changed == "code":
        code.write_text("value = 2\n")
    elif changed == "input":
        data.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        control.verify(require_commit=False)


def test_complete_blind_labels_cover_all_start_and_endpoint_boxes():
    assert control.validate_labels(*label_fixture()) == dict(start_boxes=4, endpoint_boxes=8, pairs=8)


@pytest.mark.parametrize("corruption", ["endpoint", "review", "geometry", "duplicate", "kit", "note", "predictions", "uncertain", "negative", "wrong_end", "non_person"])
def test_label_gate_rejects_incomplete_or_contradictory_evidence(corruption):
    labels, pairs, raws = label_fixture()
    if corruption == "endpoint":
        labels["records"].pop()
    elif corruption == "review":
        labels["source_review"].pop()
    elif corruption == "geometry":
        labels["records"][0]["bbox"] = [1., 2., 3., 4.]
    elif corruption == "duplicate":
        pairs["observations"][-1] = deepcopy(pairs["observations"][0])
    elif corruption == "kit":
        labels["records"][0]["kit"] = None
    elif corruption == "note":
        labels["records"][0]["visual_basis"] = ""
    elif corruption == "predictions":
        pairs["predictions_visible_during_labeling"] = True
    elif corruption == "uncertain":
        labels["source_review"][0]["status"] = "uncertain"
    elif corruption == "negative":
        pairs["pairs"][1]["right"] = pairs["pairs"][0]["right"]
    elif corruption == "wrong_end":
        pairs["pairs"][0]["right"] = "68-716-d0"
    else:
        labels["records"][0]["kit"] = "not_person"
    with pytest.raises(ValueError):
        control.validate_labels(labels, pairs, raws)


def test_changed_ids_and_real_unknown_team_additions_preserve_source_evidence():
    assert control.source_coverage(*coverage_fixture()) == dict(baseline=1, candidate=2, removed=0, added=1, changed_teams=0)


@pytest.mark.parametrize("corruption", ["loss", "box", "confidence", "duplicate_box", "duplicate_id", "time", "samples", "team", "extra_team"])
def test_source_gate_rejects_lost_altered_or_fabricated_evidence(corruption):
    raw, base, candidate = coverage_fixture()
    sample = candidate["samples"][0]
    if corruption == "loss":
        sample["persons"].pop(0)
    elif corruption == "box":
        sample["persons"][0][1] += .1
    elif corruption == "confidence":
        sample["persons"][0][-1] = .89
    elif corruption == "duplicate_box":
        sample["persons"].append([10, *sample["persons"][0][1:]])
        sample["person_teams"]["10"] = None
    elif corruption == "duplicate_id":
        sample["persons"][1][0] = 8
    elif corruption == "time":
        sample["seconds"] += .08
    elif corruption == "samples":
        candidate["samples"].clear()
    elif corruption == "team":
        sample["person_teams"]["8"] = 1
    else:
        sample["person_teams"]["9"] = 0
    with pytest.raises(ValueError):
        control.source_coverage(raw, base, candidate)


def test_replay_requires_all_seals_before_importing_or_running_a_tracker(monkeypatch):
    def missing_seal(_):
        raise ValueError("Night labels not sealed")
    monkeypatch.setattr(control, "verify_seals", missing_seal)
    monkeypatch.setattr(control.pipeline, "process_video", lambda *a, **kw: pytest.fail("Predictions opened"))
    with pytest.raises(ValueError, match="Night labels"):
        control.replay("day", {})


def test_three_arm_driver_runs_actual_trackers_and_preserves_all_source_boxes(tmp_path, monkeypatch):
    pytest.importorskip("supervision")
    from contextlib import nullcontext
    from dataclasses import asdict

    import numpy as np

    from app.tracking import deepocsort

    class Features:
        def __init__(self, _path):
            pass

        def compute_embedding(self, _bgr, boxes, _tag):
            return np.tile([[1., 0.]], (len(boxes), 1))

    cfg = control.pipeline.PipelineConfig(refine_player_identities=False,
        min_track_seconds=0., filter_off_pitch_tracks=False, max_seconds=None)
    calibration = control.PitchCalibration.from_dict(dict(image_size=[105, 68], points=[
        dict(image=[x, y], pitch=[x, y]) for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]]))
    spec = dict(segments={"68": 2040}, config=asdict(cfg), calibration=calibration.to_dict(),
                anchor=[[30., 60., 190.], [246., 246., 251.]])
    samples = [dict(order=i, frame_idx=i * 2, seconds=i * .08, continuity_id=0) for i in range(16)]
    raw = dict(samples=samples, video="synthetic.mp4", detected_persons={str(i): [
        dict(box=[20., 10., 40., 60.], confidence=.9), dict(box=[60., 10., 80., 60.], confidence=.9)]
        for i in range(16)})
    root = tmp_path / "control"
    control.write_new(root / "day/raw/seg_0068.json", raw)
    freeze = tmp_path / "freeze.json"
    freeze.write_text("{}")
    monkeypatch.setattr(control, "ROOT", root)
    monkeypatch.setattr(control, "FREEZE", freeze)
    monkeypatch.setattr(control, "seal_path", lambda _: freeze)
    monkeypatch.setattr(control, "verify", lambda: None)
    monkeypatch.setattr(control, "verify_seals", lambda _: None)
    monkeypatch.setattr(control, "decoding", nullcontext)
    monkeypatch.setattr(deepocsort, "OSNetEmbedder", Features)
    monkeypatch.setattr(control.pipeline, "video_info", lambda _: dict(fps=25., frames=32, width=105, height=68))
    rgb = np.full((68, 105, 3), [30, 60, 190], dtype=np.uint8)
    monkeypatch.setattr(control.pipeline, "iter_video_frames", lambda *a, **kw:
        iter((i, i * 2, i * .08, rgb) for i in range(16)))
    control.replay("day", dict(groups={"day": spec}))
    manifest = control.load(root / "day/predictions/manifest.json")
    assert len(manifest["comparisons"]) == 3 and len(manifest["output_sha256"]) == 3
    assert {r["backend"] for r in manifest["comparisons"]} == set(control.METHODS)
    assert all(r["coverage"] == dict(baseline=32, candidate=32, removed=0, added=0, changed_teams=0)
               for r in manifest["comparisons"])
    guarded = control.load(root / "day/predictions/guarded/seg_0068.json")
    assert guarded["summary"]["calibration_stats"]["identity_guarded"]["status"] == "applied"
    palette = control.load(root / "day/predictions/palette/seg_0068.json")
    assert "identity_consensus" in palette["summary"]["calibration_stats"]


def test_repository_control_snapshot_preserves_measured_production_code():
    if not control.FREEZE.is_file():
        pytest.skip("Control has not been frozen yet")
    snapshot = control.load(control.FREEZE)
    assert snapshot["control_pixels_opened"] is False
    assert snapshot["methods"] == list(control.METHODS)
    assert snapshot["groups"]["day"]["segments"] == {"68": 2040, "72": 2160}
    assert snapshot["groups"]["night"]["segments"] == {"74": 2220, "76": 2280}
    for name, sha in snapshot["code_sha256_lf"].items():
        assert control.code_hash(name) == sha, name
