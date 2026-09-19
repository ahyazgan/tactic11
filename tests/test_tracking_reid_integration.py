"""Recorded, warm and isolated workers must transport the same tracker profile."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from scripts import track_live, track_video


def calibration():
    return PitchCalibration.from_dict({"image_size": [100, 100], "points": [
        {"image": [x, y], "pitch": [x, y]} for x, y in [(0, 0), (90, 0), (90, 68), (0, 68)]
    ]})


def test_live_reid_transport_paths_and_restart_context(monkeypatch, tmp_path):
    from app.tracking import deepocsort

    monkeypatch.chdir(tmp_path)
    model = tmp_path / "weights" / "osnet.pth.tar"
    monkeypatch.setattr(deepocsort, "verified_model_path", lambda p: Path(p).resolve())
    captured = []
    palette = [[30., 50., 190.], [210., 215., 220.]]
    summary = {"team_colors": palette, "derived_events": {}}

    def run(cmd, **kwargs):
        if cmd[2] == "scripts.track_video":
            assert cmd[cmd.index("--tracker") + 1] == "deepocsort"
            assert cmd[cmd.index("--reid-model") + 1] == str(model)
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"summary": summary}))
            captured.append("isolated")
        return SimpleNamespace(returncode=0, stdout="frames_written: 0", stderr="")

    class Warm:
        def __init__(self, *, pipeline_kwargs, **kwargs):
            assert pipeline_kwargs["tracker_backend"] == "deepocsort"
            assert pipeline_kwargs["reid_model"] == str(model)
            self.team_anchor = None
            self.warmup_seconds = 0.

        def run(self, video, *, out_json, **kwargs):
            out_json.write_text('{"frames": []}')
            self.team_anchor = np.asarray(palette)
            captured.append("warm")
            return summary

    monkeypatch.setattr(track_live.subprocess, "run", run)
    monkeypatch.setattr(track_live, "WarmTracker", Warm)
    monkeypatch.setattr(track_live, "_stable", lambda _: True)
    for mode in ("warm", "isolated"):
        watch = tmp_path / mode
        watch.mkdir()
        (watch / "segment.mp4").write_bytes(b"test fixture")
        args = ["track_live", "--watch", str(watch), "--match-id", "1", "--home-team", "10",
                "--away-team", "20", "--camera", "static", "--tracker", "deepocsort",
                "--reid-model", "weights/osnet.pth.tar", "--once"]
        if mode == "isolated":
            args.append("--isolate")
        monkeypatch.setattr(sys, "argv", args)
        assert track_live.main() == 0
        state = track_live._load_state(watch)
        assert state["team_anchor_context"]["tracker"]["model_sha256"] == deepocsort.MODEL_SHA256
        changed = list(args)
        changed[changed.index("--tracker") + 1] = "supervision"
        monkeypatch.setattr(sys, "argv", changed)
        with pytest.raises(SystemExit) as exc:
            track_live.main()
        assert exc.value.code == 2
    assert captured == ["warm", "isolated"]


def test_recorded_cli_passes_reid_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(track_video, "video_info", lambda _: dict(width=100, height=100, fps=25., frames=10))
    monkeypatch.setattr(track_video.PitchCalibration, "load", lambda _: calibration())
    received = []

    def process(*args, **kwargs):
        received.append(kwargs["cfg"])
        return [], {"calibration_stats": {}, "derived_events": {}}

    monkeypatch.setattr(track_video, "process_video", process)
    monkeypatch.setattr(sys, "argv", ["track_video", "--video", "source.mp4", "--out",
        str(tmp_path / "out.json"), "--match-id", "1", "--home-team", "10", "--away-team", "20",
        "--camera", "static", "--calibration", "cal.json", "--tracker", "deepocsort",
        "--reid-model", "model.pth.tar"])
    assert track_video.main() == 0
    assert received[0].tracker_backend == "deepocsort"
    assert received[0].reid_model == "model.pth.tar"


@pytest.mark.parametrize("values", [dict(tracker_backend="unknown"),
    dict(tracker_backend="deepocsort", per_frame_calibration=True),
    dict(tracker_backend="deepocsort", source_name="broadcast_tracking")])
def test_unsupported_profile_fails_before_loading_detector(monkeypatch, values):
    from app.tracking.tracker_config import validate_tracker_config

    with pytest.raises(ValueError):
        validate_tracker_config(pipeline.PipelineConfig(**values), calibration())


def test_real_deepocsort_pipeline_receives_bgr_and_preserves_source_metadata(monkeypatch):
    sv = pytest.importorskip("supervision")
    pytest.importorskip("filterpy")
    from app.tracking import deepocsort

    seen = []

    class Features:
        def __init__(self, path):
            pass

        def compute_embedding(self, bgr, bbox, tag):
            assert bgr[0, 0].tolist() == [20, 60, 150]
            seen.append(len(bbox))
            return np.tile(np.array([[1., 0.]]), (len(bbox), 1))

    monkeypatch.setattr(deepocsort, "OSNetEmbedder", Features)
    monkeypatch.setattr(pipeline, "video_info", lambda _: dict(fps=25., frames=8, width=100, height=100))
    rgb = np.full((100, 100, 3), [150, 60, 20], dtype=np.uint8)
    # Missing sample order simulates a source gap even on a fixed camera.
    monkeypatch.setattr(pipeline, "iter_video_frames", lambda *a, **kw:
                        iter([(i, i * 2, i * .08, rgb) for i in [0, 1, 3, 4]]))
    d = sv.Detections(xyxy=np.array([[20., 10., 40., 60.]]), confidence=np.array([.9]))
    detector = SimpleNamespace(detect=lambda _: d, split=lambda x: (x, sv.Detections.empty()))
    cfg = pipeline.PipelineConfig(tracker_backend="deepocsort", min_track_seconds=0,
                                  filter_off_pitch_tracks=False)
    samples, teams, stats = pipeline.collect_observations("source", cfg, detector=detector,
                                                         calib=calibration(), progress=False)
    assert seen == [1, 1, 1, 1]
    assert [s.persons[0][0] for s in samples] == [1, 1, 2, 2]
    assert [s.continuity_id for s in samples] == [0, 0, 1, 1]
    assert stats["tracker_resets"] == 1
    assert stats["tracker"]["backend"] == "deepocsort"
    assert stats["tracker"]["experimental"] is True
    assert all(s.persons[0][1:] == (20., 10., 40., 60., .9) for s in samples)
    assert set(teams._obs) == {1, 2}
