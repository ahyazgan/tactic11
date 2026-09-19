"""Identity and shirt evidence stay aligned through the production pipeline."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking import pipeline
from app.tracking.calibration import PitchCalibration
from app.tracking.frames import VIDEO_PLAYER_BASE_ID
from app.tracking.teams import TeamAssigner


def calibration():
    return PitchCalibration.from_dict({"image_size": [1300, 800], "points": [
        {"image": [x * 10 + 100, y * 10 + 50], "pitch": [x, y]}
        for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]
    ]})


def samples_with_handoff():
    samples = []
    for i in range(14):
        white, blue = (230., 230., 230.), (40., 75., 150.)
        colors = {1: white if i < 8 else blue, 2: white, 3: blue, 4: blue}
        people = [(tid, 200. + tid * 60, 200., 220. + tid * 60, 270., .9) for tid in colors]
        samples.append(pipeline.SampledObservation(
            i, i * 2, i * .08, people, None,
            person_kit={str(t): colors[t] * 3 for t in colors},
        ))
    return samples


def test_refinement_splits_handoff_preserves_every_box_and_local_team():
    from app.tracking.player_identity import refine_player_tracks

    samples = samples_with_handoff()
    before = [[row[1:] for row in s.persons] for s in samples]
    assignment, stats = refine_player_tracks(samples, calibration(), fps_eff=12.5)
    assert [[row[1:] for row in s.persons] for s in samples] == before
    old, new = samples[0].persons[0][0], samples[-1].persons[0][0]
    assert old != new
    assert assignment.team_by_track[old] != assignment.team_by_track[new]
    assert len(stats["splits"]) == 1 and stats["splits"][0]["first_order"] == 8
    assert stats["splits"][0]["confirmed_order"] == 10
    for sample in samples:
        assert len({row[0] for row in sample.persons}) == len(sample.persons)
        assert sample.person_kit and sample.person_teams
        assert set(sample.person_kit) == set(sample.person_teams)
    # Replay caches can round-trip all internal observations without numpy JSON hooks.
    restored = pipeline.SampledObservation(**json.loads(json.dumps(asdict(samples[-1]))))
    assert restored.person_teams == samples[-1].person_teams


def test_unknown_fragment_survives_link_without_palette_refit(monkeypatch):
    from app.tracking import player_identity
    from app.tracking.teams import TeamAssignment

    samples = samples_with_handoff()
    palette = np.array([[230., 230., 230.], [40., 75., 150.]])
    calls = []
    def fit(bright, broad, anchor, **kwargs):
        calls.append((bright, broad))
        return TeamAssignment({t: None if t == 2 else 0 for t in bright}, palette, frozenset({2}))
    # An accepted link must not make an unknown fragment acquire its partner's shirt.
    def link(observations, **kwargs):
        ids = tuple(10 if o.track_id == 2 else o.track_id for o in observations)
        return SimpleNamespace(observation_ids=ids, links=())
    monkeypatch.setattr(player_identity, "fit_kit_evidence", fit)
    monkeypatch.setattr(player_identity, "link_identities", link)
    assignment, _ = player_identity.refine_player_tracks(samples, calibration(), fps_eff=12.5)
    assert len(calls) == 1
    np.testing.assert_array_equal(assignment.centers, palette)
    assert all(s.person_teams["10"] is None for s in samples)
    # A global assignment from another fragment cannot leak into these frames.
    frames = pipeline.build_frames(samples, {10: 0}, calibration(),
                                   match_id=1, home_team_id=20, away_team_id=30,
                                   cfg=pipeline.PipelineConfig())
    assert frames
    linked_players = [p for f in frames for p in f.players
                      if p.player_external_id == VIDEO_PLAYER_BASE_ID + 10]
    assert linked_players and all(p.team_external_id is None for p in linked_players)
    assert pipeline.observed_team(samples[0], 10, {10: 0}) is None


def test_no_colour_means_no_invented_team_or_identity_split():
    from app.tracking.player_identity import refine_player_tracks

    samples = samples_with_handoff()
    for sample in samples:
        sample.person_kit = {}
    assignment, stats = refine_player_tracks(samples, calibration(), fps_eff=12.5)
    assert not stats["splits"] and not stats["links"]
    assert set(assignment.team_by_track.values()) == {None}


def test_profile_is_fixed_camera_only_and_explicit_off_wins():
    cal = calibration()
    assert not pipeline.identity_refinement_enabled(pipeline.PipelineConfig(), cal)
    cal.meta["identity_profile"] = "fixed_camera_identity_v1"
    assert pipeline.identity_refinement_enabled(pipeline.PipelineConfig(), cal)
    assert not pipeline.identity_refinement_enabled(pipeline.PipelineConfig(refine_player_identities=False), cal)
    assert not pipeline.identity_refinement_enabled(pipeline.PipelineConfig(per_frame_calibration=True), cal)
    assert not pipeline.identity_refinement_enabled(pipeline.PipelineConfig(normalize_kit_light=True), cal)
    with pytest.raises(ValueError, match="sabit"):
        pipeline.identity_refinement_enabled(pipeline.PipelineConfig(refine_player_identities=True), None)


def test_process_video_uses_shared_refinement_for_frames_and_preview(monkeypatch):
    samples = samples_with_handoff()
    before = deepcopy(samples)
    monkeypatch.setattr(pipeline, "collect_observations", lambda *a, **kw: (
        samples, TeamAssigner(), {"effective_track_fps": 12.5}))
    previews = []
    monkeypatch.setattr(pipeline, "write_preview", lambda *a: previews.append(a))
    frames, summary = pipeline.process_video(
        "unused", calibration(), match_id=1, home_team_id=20, away_team_id=30,
        cfg=pipeline.PipelineConfig(refine_player_identities=True, preview_path="unused.mp4"),
    )
    assert frames and previews[0][1] is samples
    assert summary["team_assignment_quality"]["color_method"] == "dual_torso_v1"
    assert summary["calibration_stats"]["identity_refinement"]["splits"]
    assert samples[8].persons[0][0] != before[8].persons[0][0]
    assert all(p.identity_estimated for frame in frames for p in frame.players)


def test_different_segments_and_periods_cannot_reuse_player_or_camera_identity():
    outputs = []
    for period, offset in ((1, 0.), (1, .5), (2, 0.), (1, .5)):
        outputs.append(pipeline.build_frames(
            samples_with_handoff(), {1: 0, 2: 0, 3: 1, 4: 1}, calibration(),
            match_id=1, home_team_id=20, away_team_id=30,
            cfg=pipeline.PipelineConfig(period=period, clip_offset_minutes=offset)))
    identities = [{p.player_external_id for frame in frames for p in frame.players} for frames in outputs]
    assert identities[0].isdisjoint(identities[1])
    assert identities[1].isdisjoint(identities[2])
    assert outputs[1] == outputs[3]  # retry/restart must be deterministic
    assert len({frames[0].continuity_id for frames in outputs[:3]}) == 3


def test_warm_and_recorded_workers_export_identical_segment_identities(monkeypatch, tmp_path):
    from app.tracking.detect import DetectorConfig
    from scripts.track_live import WarmTracker

    cal = calibration()
    cal.meta["identity_profile"] = "fixed_camera_identity_v1"
    path = tmp_path / "cal.json"
    cal.save(path)
    monkeypatch.setattr(pipeline, "video_info", lambda _: {"width": 1300, "height": 800})
    monkeypatch.setattr(pipeline, "collect_observations", lambda *a, **kw: (
        samples_with_handoff(), TeamAssigner(), {"effective_track_fps": 12.5}))
    warm = WarmTracker(calibration=str(path), detector_cfg=DetectorConfig(),
                       pipeline_kwargs={}, camera="static")
    monkeypatch.setattr(warm, "_ensure_detector", lambda *a: object())
    warm._mode = {"per_frame": False, "moving": False, "reacquire": False, "source": "video_tracking"}
    target = tmp_path / "warm.json"
    warm.run(tmp_path / "clip.mp4", out_json=target, offset_minutes=.5,
             match_id=1, home_team=20, away_team=30, period=1)
    frames, _ = pipeline.process_video("unused", cal, match_id=1, home_team_id=20, away_team_id=30,
                                       cfg=pipeline.PipelineConfig(clip_offset_minutes=.5))
    actual = json.loads(target.read_text(encoding="utf-8"))
    assert actual["frames"] == [f.model_dump(mode="json") for f in frames]
    assert actual["summary"]["identity_scope"]["cross_segment_person_identity"] is False
