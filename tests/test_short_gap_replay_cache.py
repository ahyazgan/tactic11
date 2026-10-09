"""A cache must not detach secondary IDs from the source/model that produced them."""

import json
import sys
from types import SimpleNamespace

import pytest

from scripts.soccertrack_v2 import short_gap_replay_cache
from scripts.soccertrack_v2.benchmark_short_gap_motion import SingleThreadVideoReplay
from scripts.soccertrack_v2.benchmark_tracker_backends import digest
from scripts.soccertrack_v2.short_gap_replay_cache import SecondaryCache


def cache_fixture(tmp_path):
    source = tmp_path / "video-source"
    source.write_text("original source")
    prediction = tmp_path / "day/secondary/seg_0000.json"
    prediction.parent.mkdir(parents=True)
    prediction.write_text(json.dumps({"samples": []}))
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            dict(
                completed_at_utc="2026-10-09T00:00:00Z",
                versions={"example": "1"},
                input_code_sha256={str(source): digest(source)},
                output_sha256={str(prediction): digest(prediction)},
                results={"day": {"segments": {"0": {"secondary": {"profile": "test"}}}}},
            )
        )
    )
    return report, source, prediction


def test_registered_secondary_evidence_can_be_reused(tmp_path):
    report, _, _ = cache_fixture(tmp_path)
    cache = SecondaryCache(report, {"example": "1"})
    payload, stats = cache.read("day", 0)
    assert payload == {"samples": []}
    assert stats["reused_report_sha256"] == digest(report)
    cache.validate()


@pytest.mark.parametrize("change", ["version", "input", "prediction", "report", "after_read"])
def test_stale_or_changed_secondary_evidence_fails(tmp_path, change):
    report, source, prediction = cache_fixture(tmp_path)
    if change == "version":
        with pytest.raises(ValueError, match="versions"):
            SecondaryCache(report, {"example": "2"})
        return
    cache = SecondaryCache(report, {"example": "1"})
    if change == "input":
        source.write_text("changed source or model")
    elif change == "report":
        report.write_text("{}")
    else:
        if change == "after_read":
            cache.read("day", 0)
        prediction.write_text('{"samples": ["fabricated"]}')
    with pytest.raises(ValueError):
        cache.read("day", 0) if change == "prediction" else cache.validate()


def test_incomplete_report_cannot_be_reused(tmp_path):
    report, _, _ = cache_fixture(tmp_path)
    data = json.loads(report.read_text())
    del data["completed_at_utc"]
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Completed"):
        SecondaryCache(report, {"example": "1"})


def test_primary_change_does_not_exempt_secondary_model_from_validation(tmp_path, monkeypatch):
    report, primary, _ = cache_fixture(tmp_path)
    model = tmp_path / "secondary-model"
    model.write_text("model weights")
    data = json.loads(report.read_text())
    data["input_code_sha256"][str(model)] = digest(model)
    report.write_text(json.dumps(data))
    monkeypatch.setattr(short_gap_replay_cache, "EXPERIMENT_FILES", {primary.resolve()})
    primary.write_text("new primary candidate")
    cache = SecondaryCache(report, {"example": "1"})
    cache.read("day", 0)
    model.write_text("changed model")
    with pytest.raises(ValueError, match="source/code"):
        cache.validate()


@pytest.mark.parametrize("actual_threads", [1, 16])
def test_decoder_threads_are_explicit_and_verified(monkeypatch, actual_threads):
    calls, released = [], []
    capture = SimpleNamespace(
        isOpened=lambda: True, get=lambda _: actual_threads, release=lambda: released.append(True)
    )

    def factory(*args):
        calls.append(args)
        return capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(VideoCapture=factory, CAP_FFMPEG=1900, CAP_PROP_N_THREADS=70),
    )
    tracker = SimpleNamespace(max_time_lost=7)
    if actual_threads == 1:
        stream = SingleThreadVideoReplay(tracker, "source.mp4", [])
        assert stream.max_time_lost == 7
    else:
        with pytest.raises(ValueError, match="single-thread"):
            SingleThreadVideoReplay(tracker, "source.mp4", [])
        assert released == [True]
    assert calls == [("source.mp4", 1900, [70, 1])]
