from app.tracking import pipeline, pitch_bounds
from app.tracking.calibration import CalibrationPoint, PitchCalibration
from app.tracking.frames import TrackObservation, build_frame

# Görüntü = saha metresi (birim homografi): ayak noktası doğrudan saha konumu.
CALIB = PitchCalibration(points=tuple(CalibrationPoint(image=p, pitch=p) for p in ((0.0, 0.0), (105.0, 0.0), (105.0, 68.0), (0.0, 68.0))),
                         image_size=(105, 68))


def _frame(builder, players):
    return builder(match_id=1, seconds=0.0, order=0, calib=CALIB, players=players, ball=None,
                   home_team_id=10, away_team_id=20)


def _xs(frame):
    return sorted(p.x for p in frame.players)


def test_old_rule_clamps_a_person_just_outside_the_line_and_new_rule_drops_him():
    players = [TrackObservation(track_id=1, u=50.0, v=30.0, team=0), TrackObservation(track_id=2, u=-1.5, v=30.0, team=None)]
    assert _xs(_frame(build_frame, players)) == [0.0, 47.619]
    assert _xs(_frame(pitch_bounds.build_frame_inside_lines, players)) == [47.619]


def test_frame_with_only_off_pitch_people_is_empty():
    assert _frame(pitch_bounds.build_frame_inside_lines, [TrackObservation(track_id=1, u=110.0, v=30.0, team=0)]) is None


def test_install_rebinds_the_pipeline_name_only(monkeypatch):
    monkeypatch.setattr(pipeline, "build_frame", build_frame)
    pitch_bounds.install()
    assert pipeline.build_frame is pitch_bounds.build_frame_inside_lines
    from app.tracking import frames
    assert frames.build_frame is build_frame
