"""CLI and restart boundaries must preserve the same anonymous team palette."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking import pipeline
from app.tracking.anchor_state import team_anchor
from app.tracking.detect import DetectorConfig
from scripts import track_live, track_video

PALETTE = [[32., 48., 180.], [210., 210., 215.]]


def summary(colors=PALETTE):
    return {"team_colors": colors, "calibration_stats": {"calibrated_ratio": 1.0},
            "derived_events": {"derived_passes": [], "derived_defensive_actions": []}}


@pytest.mark.parametrize("invalid", [None, [], [[1, 2, 3]], [[0, 0, 0], [0, 0, 0]],
                                      [[-1, 20, 40], [200, 210, 220]],
                                      [[256, 20, 40], [200, 210, 220]],
                                      [[float("nan"), 0, 0], [200, 210, 220]], "bad"])
def test_uncertain_or_invalid_palettes_cannot_be_persisted(invalid):
    assert team_anchor(invalid) is None


def test_recorded_and_warm_operated_camera_use_same_guards_and_anchor(monkeypatch, tmp_path):
    info = {"width": 100, "height": 100, "fps": 25., "frames": 750}
    monkeypatch.setattr(track_video, "video_info", lambda _: info)
    monkeypatch.setattr(pipeline, "video_info", lambda _: info)
    received = []

    def process(*args, **kwargs):
        received.append(kwargs)
        return [], summary()

    monkeypatch.setattr(track_video, "process_video", process)
    monkeypatch.setattr(pipeline, "process_video", process)
    monkeypatch.setattr(sys, "argv", ["track_video", "--video", "segment.mp4", "--out",
        str(tmp_path / "recorded.json"), "--match-id", "1", "--home-team", "10",
        "--away-team", "20", "--camera", "operated", "--team-anchor-json", json.dumps(PALETTE)])
    assert track_video.main() == 0
    warm = track_live.WarmTracker(calibration=None, detector_cfg=DetectorConfig(model="medium"),
                                  pipeline_kwargs={}, camera="operated")
    warm.team_anchor = np.asarray(PALETTE)
    warm._calibrator = object()
    monkeypatch.setattr(warm, "_ensure_detector", lambda *_: object())
    warm.run(tmp_path / "segment.mp4", out_json=tmp_path / "warm.json", offset_minutes=0,
             match_id=1, home_team=10, away_team=20, period=1)
    assert len(received) == 2
    for call in received:
        cfg = call["cfg"]
        assert cfg.per_frame_calibration and cfg.allow_reacquire
        assert not cfg.detect_cuts and not cfg.detect_replays
        np.testing.assert_array_equal(call["team_anchor"], PALETTE)
    assert json.loads((tmp_path / "recorded.json").read_text())["frames"] == []


@pytest.mark.parametrize("value", ['not-json', '[[0,0,0],[0,0,0]]', '[[NaN,0,0],[255,255,255]]'])
def test_invalid_cli_anchor_rejected_before_video_or_model_load(monkeypatch, tmp_path, value):
    monkeypatch.setattr(track_video, "video_info", lambda _: pytest.fail("video opened"))
    monkeypatch.setattr(sys, "argv", ["track_video", "--video", "missing.mp4", "--out",
        str(tmp_path / "out.json"), "--match-id", "1", "--home-team", "10", "--away-team", "20",
        "--team-anchor-json", value])
    with pytest.raises(SystemExit) as exc:
        track_video.main()
    assert exc.value.code == 2


def test_isolated_live_preserves_first_anchor_and_restores_it_in_both_modes(monkeypatch, tmp_path):
    for n in range(3):
        (tmp_path / f"segment{n}.mp4").write_bytes(b"test input")
    monkeypatch.setattr(track_live, "_stable", lambda _: True)
    anchors = []
    offsets = []
    palettes = iter([[[0, 0, 0], [0, 0, 0]], PALETTE, PALETTE[::-1], PALETTE[::-1]])

    def run(cmd, **kwargs):
        if cmd[2] == "scripts.track_video":
            anchors.append(json.loads(cmd[cmd.index("--team-anchor-json") + 1])
                           if "--team-anchor-json" in cmd else None)
            offsets.append(float(cmd[cmd.index("--clip-offset-minutes") + 1]))
            assert cmd[cmd.index("--camera") + 1] == "operated"
            assert cmd[cmd.index("--refine-identities") + 1] == "off"
            from pathlib import Path
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"frames": [], "summary": summary(next(palettes))}))
        return SimpleNamespace(returncode=0, stdout="frames_written: 0", stderr="")

    monkeypatch.setattr(track_live.subprocess, "run", run)
    args = ["track_live", "--watch", str(tmp_path), "--match-id", "1", "--home-team", "10",
            "--away-team", "20", "--camera", "operated", "--refine-identities", "off",
            "--segment-seconds", "0.123", "--once"]
    monkeypatch.setattr(sys, "argv", args + ["--isolate"])
    assert track_live.main() == 0
    assert anchors == [None, None, PALETTE]
    np.testing.assert_allclose(offsets, [0, .123 / 60, .246 / 60], rtol=0, atol=1e-15)
    assert track_live._load_state(tmp_path)["team_anchor"] == PALETTE

    (tmp_path / "segment3.mp4").write_bytes(b"test input")
    assert track_live.main() == 0
    assert anchors[-1] == PALETTE  # restarted isolated worker

    class FakeWarm:
        def __init__(self, **kwargs):
            self.team_anchor = None
            self.warmup_seconds = 0.

        def run(self, video, *, out_json, **kwargs):
            np.testing.assert_array_equal(self.team_anchor, PALETTE)
            out_json.write_text('{"frames": []}')
            return summary(PALETTE[::-1])

    monkeypatch.setattr(track_live, "WarmTracker", FakeWarm)
    monkeypatch.setattr(sys, "argv", args)
    (tmp_path / "segment4.mp4").write_bytes(b"test input")
    assert track_live.main() == 0
    assert track_live._load_state(tmp_path)["team_anchor"] == PALETTE
    for flag, value in [("--home-team", "999"), ("--camera", "static"),
                        ("--per-frame-calibration", "off"), ("--reacquire", "off")]:
        changed = list(args)
        if flag in changed:
            changed[changed.index(flag) + 1] = value
        else:
            changed += [flag, value]
        monkeypatch.setattr(sys, "argv", changed)
        with pytest.raises(SystemExit) as exc:
            track_live.main()
        assert exc.value.code == 2  # incompatible palette contexts cannot be mixed


@pytest.mark.parametrize("explicit_onnx", [False, True])
def test_live_model_paths_match_between_warm_and_isolated_from_other_directory(
        monkeypatch, tmp_path, explicit_onnx):
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    expected_weights = str(tmp_path / "weights")
    expected_onnx = str(tmp_path / ("custom/model.onnx" if explicit_onnx
                                   else "data/tracking/models/onnx/weights.onnx"))
    captured = []

    def run(cmd, **kwargs):
        if cmd[2] == "scripts.track_video":
            assert kwargs["cwd"] == str(track_live.PROJECT_ROOT)
            assert cmd[cmd.index("--weights") + 1] == expected_weights
            assert cmd[cmd.index("--onnx-model") + 1] == expected_onnx
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"summary": summary()}))
            captured.append("isolated")
        return SimpleNamespace(returncode=0, stdout="frames_written: 0", stderr="")

    class FakeWarm:
        def __init__(self, *, detector_cfg, **kwargs):
            assert detector_cfg.weights == expected_weights
            assert detector_cfg.onnx_model == expected_onnx
            self.team_anchor = None
            self.warmup_seconds = 0.

        def run(self, video, *, out_json, **kwargs):
            out_json.write_text('{"frames": []}')
            captured.append("warm")
            return summary()

    monkeypatch.setattr(track_live.subprocess, "run", run)
    monkeypatch.setattr(track_live, "WarmTracker", FakeWarm)
    monkeypatch.setattr(track_live, "_stable", lambda _: True)
    for mode in ("warm", "isolated"):
        watch = tmp_path / mode
        watch.mkdir()
        (watch / "segment.mp4").write_bytes(b"source")
        args = ["track_live", "--watch", mode, "--match-id", "1", "--home-team", "10",
                "--away-team", "20", "--camera", "static", "--weights", "weights", "--once"]
        if explicit_onnx:
            args += ["--onnx-model", "custom/model.onnx"]
        if mode == "isolated":
            args += ["--isolate"]
        monkeypatch.setattr(sys, "argv", args)
        assert track_live.main() == 0
    assert captured == ["warm", "isolated"]
