"""Field evidence removes perimeter clutter without discarding stationary/throw-in players."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from app.tracking.calibration import PitchCalibration
from app.tracking.person_filter import annotated_boundary, filter_person_tracks, inside_boundary
from app.tracking.pipeline import SampledObservation


def calibration():
    return PitchCalibration.from_dict({"image_size": [1200, 800], "points": [
        {"image": [100, 100], "pitch": [0, 0]}, {"image": [1150, 100], "pitch": [105, 0]},
        {"image": [1150, 780], "pitch": [105, 68]}, {"image": [100, 780], "pitch": [0, 68]}]})


def samples():
    return [SampledObservation(i, i * 2, i * .08, [
        (1, 490, 450, 510, 500, .9),  # still player, always on field
        (2, 100, 740, 120, 785 if i == 0 else 775, .9),  # temporary sideline excursion
        (3, 480, 780, 530, 796, .99),  # high-confidence stationary printing
        (4, 90, 80, 110, 100, .9),  # precisely on touchline
    ], None) for i in range(3)]


def test_perimeter_rejects_only_tracks_without_field_support_and_preserves_boxes():
    data = samples()
    original = [list(s.persons) for s in data]
    result = filter_person_tracks(data, calibration())
    assert result["applied"] and result["tracks_removed"] == 1 and result["observations_removed"] == 3
    for before, after in zip(original, data, strict=True):
        assert after.persons == [p for p in before if p[0] != 3]


def test_support_does_not_cross_a_camera_cut_even_if_track_number_repeats():
    data = samples()
    data.append(SampledObservation(3, 6, .24, [(1, 480, 780, 530, 796, .99)], None, continuity_id=1))
    filter_person_tracks(data, calibration())
    assert data[-1].persons == []
    assert all(any(p[0] == 1 for p in s.persons) for s in data[:-1])


@pytest.mark.parametrize("case,reason", [("disabled", "disabled"), ("none", "no_static_calibration"),
    ("partial", "incomplete_or_invalid_annotated_boundary"), ("dynamic", "changing_calibration")])
def test_missing_or_inapplicable_boundary_preserves_observations(case, reason):
    data, cal = samples(), calibration()
    if case == "none":
        cal = None
    elif case == "partial":
        cal = replace(cal, points=tuple(replace(p, pitch=(p.pitch[0]+1, p.pitch[1]+1)) for p in cal.points))
    elif case == "dynamic":
        data[0].calibration = cal
    before = [list(s.persons) for s in data]
    result = filter_person_tracks(data, cal, enabled=case != "disabled")
    assert result["skip_reason"] == reason and not result["applied"]
    assert [s.persons for s in data] == before


def test_curved_boundary_uses_edge_samples_and_rejects_incomplete_tps_perimeter():
    cal = calibration()
    from app.tracking.calibration import CalibrationPoint
    mids = (CalibrationPoint((625, 50), (52.5, 0)), CalibrationPoint((1170, 440), (105, 34)),
            CalibrationPoint((625, 700), (52.5, 68)), CalibrationPoint((80, 440), (0, 34)))
    curved = replace(cal, method="tps", points=cal.points + mids)
    polygon = annotated_boundary(curved)
    assert polygon is not None
    np.testing.assert_array_equal(inside_boundary(np.array([[625, 750], [625, 699], [625, 701]]), polygon, 2),
                                  [False, True, True])
    incomplete = replace(curved, points=cal.points + mids[:-1] + (CalibrationPoint((500, 400), (40, 30)),))
    assert annotated_boundary(incomplete) is None


def test_invalid_crossed_boundary_and_nonfinite_feet_are_rejected():
    cal = calibration()
    points = list(cal.points)
    points[1] = replace(points[1], image=cal.points[2].image)
    points[2] = replace(points[2], image=cal.points[1].image)
    assert annotated_boundary(replace(cal, points=tuple(points))) is None
    polygon = annotated_boundary(cal)
    assert polygon is not None
    np.testing.assert_array_equal(inside_boundary(np.array([[np.nan, 500], [np.inf, 500]]), polygon, 2), [False, False])


def test_empty_clip_is_valid_and_single_inside_hit_is_insufficient():
    assert filter_person_tracks([], calibration())["observations_removed"] == 0
    data = samples()[:1]
    filter_person_tracks(data, calibration())
    assert data[0].persons == []


def test_production_collection_excludes_perimeter_tracks_from_palette(monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.tracking import pipeline

    class Detections:
        def __init__(self, boxes, ids):
            self.xyxy = np.asarray(boxes, dtype=float).reshape(-1, 4)
            self.tracker_id = np.asarray(ids)
            self.confidence = np.full(len(ids), .95)
        def __len__(self):
            return len(self.xyxy)
        def __getitem__(self, mask):
            return Detections(self.xyxy[mask], self.tracker_id[mask])

    persons = Detections([[490, 450, 510, 500], [600, 450, 620, 500], [700, 780, 720, 796]], [1, 2, 3])
    tracker = SimpleNamespace(update_with_detections=lambda d: d)
    monkeypatch.setitem(sys.modules, "supervision", SimpleNamespace(ByteTrack=lambda **kw: tracker))
    monkeypatch.setattr(pipeline, "video_info", lambda _: {"fps": 25, "width": 1200, "height": 800})
    monkeypatch.setattr(pipeline, "iter_video_frames", lambda *a: iter([(i,i*2,i*.08,np.zeros((1,1,3))) for i in range(2)]))
    monkeypatch.setattr(pipeline, "kit_color", lambda rgb, box, **kw: np.array([30, 60, 200]) if box[0] < 550
                        else np.array([220, 220, 220]) if box[0] < 650 else np.array([200, 0, 0]))
    detector = SimpleNamespace(detect=lambda _: None, split=lambda _: (persons, Detections([], [])))
    frames, summary = pipeline.process_video("unused", calibration(), match_id=1, home_team_id=0, away_team_id=1,
        cfg=pipeline.PipelineConfig(min_track_seconds=0, filter_off_pitch_tracks=True), detector=detector)
    assert summary["calibration_stats"]["person_filter"]["tracks_removed"] == 1
    assert summary["tracks"] == 2 and summary["team_counts"]["unassigned"] == 0
    assert len(frames[0].players) == 2


@pytest.mark.parametrize("override,validated,expected", [(None,False,False), (None,True,True),
                                                       (False,True,False), (True,False,True)])
def test_default_requires_validated_camera_profile_and_respects_explicit_override(override, validated, expected):
    from app.tracking.pipeline import PipelineConfig, person_filter_enabled

    cal = calibration()
    if validated:
        cal = replace(cal, meta={"person_filter_profile": "annotated_perimeter_track_v1"})
    assert person_filter_enabled(PipelineConfig(filter_off_pitch_tracks=override), cal) == expected


def test_only_validated_daylight_profile_enables_filter_automatically():
    from app.tracking.pipeline import PipelineConfig, person_filter_enabled

    day = PitchCalibration.load("data/tracking/calibrations/soccertrack_v2_117093_landmarks.json")
    night = PitchCalibration.load("data/tracking/calibrations/soccertrack_v2_117092_landmarks.json")
    assert person_filter_enabled(PipelineConfig(), day)
    assert not person_filter_enabled(PipelineConfig(), night)
    assert not person_filter_enabled(PipelineConfig(), None)


def test_control_labels_cannot_change_perimeter_filter_or_team_mapping():
    import copy
    from dataclasses import asdict

    from scripts.soccertrack_v2.benchmark_person_filter import evaluate

    data = {"samples": [asdict(s) for s in samples()], "calibration": calibration().to_dict(),
            "colors": {str(t): [c,c] for t,c in [(1,[30,60,200]),(2,[220,220,220]),
                                              (3,[220,220,220]),(4,[30,60,200])]}}
    mapping = [{"id": f"0-0-{t}", "segment": 0,"frame_idx": 0,"track": t,"kit": k}
               for t,k in [(1,"blue"),(2,"white"),(3,"not_person"),(4,"blue")]]
    control = [{**r, "segment": 3, "id": r["id"].replace("0-0-", "3-0-")} for r in mapping]
    flipped = [{**r,"kit": "white" if r["kit"]=="blue" else "blue" if r["kit"]=="white" else r["kit"]}
               for r in control]
    before = evaluate({0:data,3:copy.deepcopy(data)},mapping,control)
    after = evaluate({0:data,3:copy.deepcopy(data)},mapping,flipped)
    for method in before:
        assert before[method]["predictions"] == after[method]["predictions"]
        assert before[method]["retained_ids"] == after[method]["retained_ids"]
        assert before[method]["blue_team_from_mapping"] == after[method]["blue_team_from_mapping"]


@pytest.mark.parametrize("source,track,output", [(25,15,5), (30,15,5), (25,15,12.5), (24,8,5)])
def test_preview_frames_belong_to_observation_grid_at_actual_playback_rate(source, track, output):
    from app.tracking.pipeline import PipelineConfig, output_stride, preview_fps, sample_stride

    cfg = PipelineConfig(track_fps=track, fps_out=output)
    fps = preview_fps(source, cfg)
    stride = sample_stride(source, fps)
    assert stride == sample_stride(source, track) * output_stride(cfg)
    assert fps == pytest.approx(source / stride)
    assert set(range(0, source*30, stride)) <= set(range(0, source*30, sample_stride(source, track)))


def test_panorama_preview_draws_annotated_curve_without_inverse_homography(monkeypatch):
    import sys
    from types import SimpleNamespace

    from app.tracking.pipeline import _draw_pitch_lines

    cal = PitchCalibration.load("data/tracking/calibrations/soccertrack_v2_117093_landmarks.json")
    drawn = []
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(polylines=lambda image, points, **kw: drawn.append((points,kw))))
    monkeypatch.setattr(np.linalg, "inv", lambda *a: pytest.fail("panorama must not invert homography"))
    _draw_pitch_lines(np.zeros((1,1,3)), cal)
    assert len(drawn) == 2
    np.testing.assert_array_equal(drawn[0][0][0], np.rint(annotated_boundary(cal)))
    assert drawn[0][1]["isClosed"] and not drawn[1][1]["isClosed"]


def test_preview_resize_matches_writer_dimensions_for_nonintegral_panorama_scale(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace

    from app.tracking import pipeline

    written = []
    class Writer:
        def __init__(self, path, codec, fps, size):
            self.size = size
            assert fps == pytest.approx(25/6)
        def isOpened(self):
            return True
        def write(self, frame):
            assert (frame.shape[1],frame.shape[0]) == self.size == (1600,422)
            written.append(self.size)
        def release(self):
            written.append("released")
    cv = SimpleNamespace(VideoWriter=Writer, VideoWriter_fourcc=lambda *a: 0, COLOR_RGB2BGR=0, INTER_AREA=0,
        cvtColor=lambda f,*a: f, resize=lambda f,size,**kw: np.zeros((size[1],size[0],3),dtype=np.uint8))
    monkeypatch.setitem(sys.modules,"cv2",cv)
    monkeypatch.setattr(pipeline,"video_info",lambda _: {"fps":25})
    monkeypatch.setattr(pipeline,"iter_video_frames",lambda *a: iter([(0,0,0.,np.zeros((1080,4096,3),dtype=np.uint8))]))
    pipeline.write_preview("unused",[],{},None,pipeline.PipelineConfig(),tmp_path/"preview.mp4")
    assert written == [(1600,422),"released"]


def test_frozen_filter_hash_ignores_checkout_line_endings_but_detects_code_change(tmp_path):
    from scripts.soccertrack_v2.benchmark_person_filter import filter_digest

    path = tmp_path / "filter.py"
    path.write_bytes(b"threshold = 2\n")
    original = filter_digest(path)
    path.write_bytes(b"threshold = 2\r\n")
    assert filter_digest(path) == original
    path.write_bytes(b"threshold = 3\r\n")
    assert filter_digest(path) != original
