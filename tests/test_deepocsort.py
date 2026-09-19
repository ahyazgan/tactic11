"""Exercise real association, source evidence and independent stream lifetimes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.tracking.deepocsort import DeepOCSortTracker, verified_model_path


@pytest.fixture
def source():
    sv = pytest.importorskip("supervision")
    pytest.importorskip("filterpy")
    return sv.Detections(xyxy=np.array([[10., 10., 30., 80.], [60., 10., 80., 80.]]),
        confidence=np.array([.9, .8]), class_id=np.array([0, 0]),
        data={"raw_index": np.array([42, 73]), "label": np.array(["left", "right"])})


class Features:
    """Deterministic features for algorithm contracts, not model accuracy claims."""

    def __init__(self):
        self.calls = []

    def compute_embedding(self, img, bbox, tag):
        self.calls.append(bbox.copy())
        return np.tile(np.array([[1., 0.]]), (len(bbox), 1))


def image():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def tracker(**kwargs):
    return DeepOCSortTracker(threshold=.25, lost_frames=2, **kwargs)


@pytest.mark.parametrize("appearance", [False, True])
def test_real_association_preserves_exact_rows_through_short_gap(source, appearance):
    model = Features()
    t = tracker(appearance=appearance, embedder=model)
    for _ in range(3):
        first = t.update_with_detections(source, image())
    ids = dict(zip(first.data["raw_index"], first.tracker_id, strict=True))
    calls = len(model.calls)
    assert len(t.update_with_detections(source[:0], image())) == 0
    assert len(model.calls) == calls
    after = t.update_with_detections(source, image())
    assert dict(zip(after.data["raw_index"], after.tracker_id, strict=True)) == ids
    for i, row in enumerate(after.data["raw_index"]):
        index = np.flatnonzero(source.data["raw_index"] == row)[0]
        assert np.array_equal(after.xyxy[i], source.xyxy[index])
        assert after.confidence[i] == source.confidence[index]
        assert after.data["label"][i] == source.data["label"][index]
    assert source.tracker_id is None


def test_duplicate_geometry_is_not_used_to_guess_source_indices(source):
    source.xyxy[1] = source.xyxy[0]
    t = tracker(appearance=False)
    out = t.update_with_detections(source, image())
    assert set(out.data["raw_index"]) == {42, 73}
    assert len(set(out.tracker_id)) == 2
    by_row = dict(zip(out.data["raw_index"], out.confidence, strict=True))
    assert by_row == {42: .9, 73: .8}


def test_interleaved_streams_and_reset_do_not_share_id_counter(source):
    a = tracker(appearance=False)
    assert a.update_with_detections(source[:1], image()).tracker_id.tolist() == [1]
    b = tracker(appearance=False)
    assert b.update_with_detections(source, image()).tracker_id.tolist() == [2, 1]
    a.update_with_detections(source, image())
    assert a.tracker.next_id == 2
    b.reset()
    b.update_with_detections(source[:1], image())
    assert b.tracker.next_id == 1
    assert a.tracker.next_id == 2


def test_expiry_and_reset_discard_appearance_history(source):
    t = tracker(embedder=Features())
    for _ in range(3):
        t.update_with_detections(source[:1], image())
    for _ in range(3):
        t.update_with_detections(source[:0], image())
    assert t.tracker.trackers == []
    t.update_with_detections(source[:1], image())
    after = t.update_with_detections(source[:1], image())
    assert after.tracker_id.tolist() == [2]
    t.reset()
    assert t.tracker.trackers == []
    assert t.update_with_detections(source[:1], image()).tracker_id.tolist() == [1]


def test_strict_threshold_is_filtered_before_appearance_and_keeps_original_indices(source):
    source.confidence[0] = .25
    model = Features()
    t = tracker(embedder=model)
    out = t.update_with_detections(source, image())
    assert out.data["raw_index"].tolist() == [73]
    assert np.array_equal(model.calls[0], source.xyxy[1:])


@pytest.mark.parametrize("bad", ["nan_box", "nan_conf", "zero_box", "negative_conf", "image"])
def test_invalid_input_fails_before_advancing_tracker(source, bad):
    bgr = image()
    if bad == "nan_box":
        source.xyxy[0, 0] = np.nan
    elif bad == "nan_conf":
        source.confidence[0] = np.nan
    elif bad == "zero_box":
        source.xyxy[0, 2] = source.xyxy[0, 0]
    elif bad == "negative_conf":
        source.confidence[0] = -.1
    else:
        bgr = bgr.astype(float)
    t = tracker(appearance=False)
    with pytest.raises(ValueError):
        t.update_with_detections(source, bgr)
    assert t.tracker.frame_count == 0


@pytest.mark.parametrize("output", [
    [[0, 0, 1, 1, 1, 99]], [[0, 0, 1, 1, 0, 0]],
    [[0, 0, 1, 1, 1, .5]], [[0, 0, 1, 1, 1.5, 0]],
    [[0, 0, 1, 1, 1, 0], [0, 0, 1, 1, 1, 1]],
    [[0, 0, 1, 1, 1, 0], [0, 0, 1, 1, 2, 0]],
])
def test_invalid_output_cannot_enter_evidence(source, monkeypatch, output):
    t = tracker(appearance=False)
    monkeypatch.setattr(t.tracker, "update", lambda *a, **kw: np.asarray(output, dtype=float))
    with pytest.raises(ValueError, match="invalid source"):
        t.update_with_detections(source, image())


def test_missing_or_wrong_model_is_rejected_without_unpickling(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        verified_model_path(str(tmp_path / "missing"))
    model = tmp_path / "model"
    model.write_bytes(b"untrusted checkpoint")
    with pytest.raises(ValueError, match="SHA-256"):
        verified_model_path(str(model))


def test_vendored_code_matches_recorded_adaptations():
    root = Path("app/tracking/_vendor/deepocsort")
    manifest = json.loads((root / "provenance.json").read_text())
    assert manifest["commit"] == "6bb51d027b137233f5c520b6fcc4f2ae387a6ba9"
    for name, hashes in manifest["files"].items():
        actual = hashlib.sha256((root / name).read_text(encoding="utf-8").encode()).hexdigest()
        assert actual == hashes["adapted_sha256_lf"]
