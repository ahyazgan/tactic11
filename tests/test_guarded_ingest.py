"""Retrospective identity splits survive video JSON, SQLite and domain reload."""
import json
from types import SimpleNamespace

import numpy as np

from app.api.tracking import frames_in_window
from app.data.ingest.tracking import ingest_tracking_match
from app.data.sources.video_tracking import VideoJsonTrackingSource
from app.tracking.calibration import PitchCalibration
from app.tracking.frames import frames_to_json
from app.tracking.guarded_identity import GuardedTeamAssigner
from app.tracking.pipeline import PipelineConfig, SampledObservation, build_frames
from app.tracking.teams import TeamAssignment


def test_guarded_delayed_split_and_segment_namespace_roundtrip(session, tmp_path):
    palette = np.array([[30., 60., 190.], [246., 246., 251.]])
    cal = PitchCalibration.from_dict({"image_size": [105, 68], "points": [
        {"image": [x, y], "pitch": [x, y]} for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]]})
    outputs = []
    for offset in (0., .5):
        cfg = PipelineConfig(tracker_backend="guarded", fps_out=10., track_fps=10.,
            min_track_seconds=0., filter_off_pitch_tracks=False, clip_offset_minutes=offset)
        assigner, samples = GuardedTeamAssigner(), []
        for order in range(16):
            box = [float(order), 0., float(order + 20), 50.]
            sample = SampledObservation(order, order * 2, order / 10., [(100, *box, .9)], None)
            def stream(identity, box=box):
                return SimpleNamespace(tracker_id=np.array([identity]), xyxy=np.array([box]), confidence=np.array([.9]))
            assigner.record_frame(sample, SimpleNamespace(
                last_source=[dict(box=box, confidence=.9, color=palette[int(order >= 7)].tolist())],
                last_recovery=stream(100), last_secondary=stream(200 if order < 7 else 201),
                recovery_offset=0, last_motion=[]))
            samples.append(sample)
        assignment, stats = assigner.refine(samples,
            TeamAssignment({100: 0}, palette, frozenset()), cal, cfg, 10., palette)
        assert stats["boundaries"][0]["first_order"] == 7
        assert stats["boundaries"][0]["confirmed_order"] == 9
        frames = build_frames(samples, assignment.team_by_track, cal,
            match_id=991010, home_team_id=217, away_team_id=213, cfg=cfg)
        path = tmp_path / f"segment-{offset}.json"
        path.write_text(json.dumps(frames_to_json(frames, match_id=991010)), encoding="utf-8")
        source = VideoJsonTrackingSource(path)
        report = ingest_tracking_match(session, source, match_external_id=991010)
        assert report.frames_written == len(frames)
        repeat = ingest_tracking_match(session, source, match_external_id=991010)
        assert repeat.frames_written == 0 and repeat.frames_updated == len(frames)
        outputs.extend(frames)
    session.commit()
    loaded = frames_in_window(session, 991010, from_minute=0., to_minute=1.)

    def identity_rows(frames):
        return [(f.period, f.minute, f.continuity_id,
            [(p.player_external_id, p.team_external_id, p.x, p.y) for p in f.players]) for f in frames]

    assert identity_rows(loaded) == identity_rows(outputs)
    assert len({p.player_external_id for f in loaded for p in f.players}) == 4
    assert {p.team_external_id for f in loaded for p in f.players} == {217}
