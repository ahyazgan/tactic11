"""Production evidence transport, deferred decisions and reset isolation."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking import guarded_identity, pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.guarded_identity import GuardedTeamAssigner
from app.tracking.teams import TeamAssignment
from app.tracking.tracker_config import tracker_context, validate_tracker_config

PALETTE = np.array([[30., 60., 190.], [246., 246., 251.]])


def calibration():
    return PitchCalibration.from_dict({"image_size": [105, 68], "points": [
        {"image": [x, y], "pitch": [x, y]} for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]]})


def detections(rows):
    return SimpleNamespace(tracker_id=np.array([r[0] for r in rows]),
        xyxy=np.array([r[1:5] for r in rows]).reshape(-1, 4), confidence=np.array([r[5] for r in rows]))


def evidence(*, missing=False, extra=False):
    assigner, samples = GuardedTeamAssigner(), []
    for order in range(16):
        row = (100, float(order), 0., float(order + 20), 50., .9)
        sample = pipeline.SampledObservation(order, order * 2, order / 10, [row], (40., 50., .7), "roi")
        source = [dict(box=list(row[1:5]), confidence=.9, color=PALETTE[int(order >= 7)].tolist())]
        recovery = [] if missing and order == 0 else [row]
        if extra and order == 0:
            recovery = [*recovery, (150, 60., 0., 80., 50., .8)]
            source.append(dict(box=[60., 0., 80., 50.], confidence=.8, color=None))
        tracker = SimpleNamespace(last_source=source, last_recovery=detections(recovery),
            recovery_offset=0, last_secondary=detections([(200 if order < 7 else 201, *row[1:])]),
            last_motion=[])
        assigner.record_frame(sample, tracker)
        samples.append(sample)
    assignment = TeamAssignment({100: 0}, PALETTE.copy(), frozenset())
    cfg = pipeline.PipelineConfig(tracker_backend="guarded", min_track_seconds=0,
        filter_off_pitch_tracks=False, fps_out=10, track_fps=10)
    return assigner, samples, assignment, cfg


@pytest.mark.parametrize("missing", [False, True])
def test_real_refinement_retains_ball_metadata_and_source_teams_with_clip_fallback(missing):
    assigner, samples, assignment, cfg = evidence(missing=missing, extra=True)
    original = deepcopy(samples)
    final, stats = assigner.refine(samples, assignment, calibration(), cfg, 10., PALETTE)
    assert len(stats["boundaries"]) == 1
    assert stats["boundaries"][0]["first_order"] == 7
    assert stats["boundaries"][0]["confirmed_order"] == 9
    assert bool(stats["recovery_fallback"]) == missing
    assert stats["boxes_created"] == int(not missing)
    for before, after in zip(original, samples, strict=True):
        assert after.ball == before.ball and after.ball_source == before.ball_source
        assert after.persons[0][1:] == before.persons[0][1:]
        assert after.person_teams[str(after.persons[0][0])] == 0
    if not missing:
        assert samples[0].person_teams["150"] is None and final.team_by_track[150] is None
    frames = pipeline.build_frames(samples, final.team_by_track, calibration(),
        match_id=1, home_team_id=10, away_team_id=20, cfg=cfg)
    assert frames and any(f.ball for f in frames)
    assert len({p.player_external_id for f in frames for p in f.players}) == (2 if missing else 3)


def test_missing_anchor_is_explicit_baseline_warmup_without_refitting_or_mutation():
    assigner, samples, assignment, cfg = evidence(extra=True)
    original = deepcopy(samples)
    final, stats = assigner.refine(samples, assignment, calibration(), cfg, 10., None)
    assert final is assignment and samples == original
    assert stats["status"] == "baseline_warmup_missing_fixed_palette"
    assert stats["boundaries"] == [] and stats["boxes_created"] == 0


@pytest.mark.parametrize("anchor", [[[0, 0, 0], [0, 0, 0]], [[-1, 20, 30], [250, 250, 250]], [[1, 2]]])
def test_invalid_fixed_palette_fails_before_source_or_model_load(monkeypatch, anchor):
    monkeypatch.setattr(pipeline, "collect_observations", lambda *a, **k: pytest.fail("source opened"))
    with pytest.raises(ValueError, match="palette"):
        pipeline.process_video("unused", calibration(), cfg=pipeline.PipelineConfig(tracker_backend="guarded"),
            team_anchor=anchor, match_id=1, home_team_id=10, away_team_id=20)


@pytest.mark.parametrize("change", ["camera", "light", "refiner", "calibration", "implicit_refiner"])
def test_unsupported_guarded_configuration_fails(change):
    cfg = pipeline.PipelineConfig(tracker_backend="guarded")
    cal = SimpleNamespace(meta={})
    if change == "camera":
        cfg.source_name = "broadcast_tracking"
    elif change == "light":
        cfg.normalize_kit_light = True
    elif change == "refiner":
        cfg.refine_player_identities = True
    elif change == "calibration":
        cfg.per_frame_calibration = True
    else:
        cal.meta["identity_profile"] = "fixed_camera_identity_v1"
    with pytest.raises(ValueError):
        validate_tracker_config(cfg, cal)


def test_guarded_live_profile_cannot_reuse_old_consensus_anchor_context(monkeypatch):
    from pathlib import Path

    from app.tracking import deepocsort

    monkeypatch.setattr(deepocsort, "verified_model_path", lambda _: Path("verified"))
    guarded = tracker_context("guarded", "model")
    assert guarded["tracker"]["profile"] == guarded_identity.PROFILE
    assert guarded != tracker_context("consensus", "model")
    assert guarded != tracker_context("deepocsort", "model")


def test_actual_trackers_reset_recovery_namespace_and_keep_original_baseline(monkeypatch):
    sv = pytest.importorskip("supervision")
    from app.tracking import deepocsort

    class Features:
        def __init__(self, path):
            pass

        def compute_embedding(self, bgr, bbox, tag):
            assert bgr[0, 0].tolist() == [190, 60, 30]
            return np.tile([[1., 0.]], (len(bbox), 1))

    monkeypatch.setattr(deepocsort, "OSNetEmbedder", Features)
    monkeypatch.setattr(pipeline, "video_info", lambda _: dict(fps=25., frames=14, width=105, height=68))
    rgb = np.full((68, 105, 3), [30, 60, 190], dtype=np.uint8)
    # A real skipped source sample triggers the shared reset, including recovery.
    monkeypatch.setattr(pipeline, "iter_video_frames", lambda *a, **kw:
        iter([(i, i * 2, i * .08, rgb) for i in [0, 1, 2, 4, 5, 6]]))
    source = sv.Detections(xyxy=np.array([[20., 10., 40., 60.]]), confidence=np.array([.9]))
    detector = SimpleNamespace(detect=lambda _: source, split=lambda d: (d, sv.Detections.empty()))
    cfg = pipeline.PipelineConfig(tracker_backend="guarded", min_track_seconds=0,
        filter_off_pitch_tracks=False, refine_player_identities=False)
    samples, assigner, stats = pipeline.collect_observations("source", cfg, detector=detector,
        calib=calibration(), progress=False)
    baseline = deepcopy(samples)
    assignment = assigner.fit(PALETTE, eligible_tracks={p[0] for s in samples for p in s.persons})
    assigner.refine(samples, assignment, calibration(), cfg, 12.5, PALETTE)
    assert [s.persons[0][0] for s in samples] == [1, 1, 1, 2, 2, 2]
    assert [s.continuity_id for s in samples] == [0, 0, 0, 1, 1, 1]
    assert [s.persons for s in samples] == [s.persons for s in baseline]
    assert stats["tracker_resets"] == 1 and stats["tracker"]["experimental"]
    assert set(assigner._obs) == {1, 2}
