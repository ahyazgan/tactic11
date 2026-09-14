"""Local illumination must preserve kit colour, bounds and the collection path."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from app.tracking.teams import TeamAssigner, kit_color, normalize_kit_light, torso_color

BOX = (30, 10, 50, 90)


def shirt_frame(shirt, brightness=1.0):
    frame = np.full((100, 80, 3), [40, 80, 40], dtype=np.uint8)
    frame[10:90, 30:50] = shirt
    return (frame * brightness).astype(np.uint8)


def test_local_light_keeps_both_kits_stable_when_field_and_shirt_enter_shadow():
    assigner = TeamAssigner(min_observations=1)
    for track, shirt in enumerate(([40, 60, 120], [200, 200, 180])):
        bright, shadow = shirt_frame(shirt), shirt_frame(shirt, .5)
        before = shadow.copy()
        np.testing.assert_allclose(kit_color(bright, BOX), kit_color(shadow, BOX))
        np.testing.assert_allclose(torso_color(shadow, BOX), np.array(shirt) * .5)
        np.testing.assert_allclose(kit_color(shadow, BOX, normalize_light=False), torso_color(shadow, BOX))
        np.testing.assert_array_equal(shadow, before)
        assigner.observe(track, kit_color(bright, BOX))
        assigner.observe(track + 2, kit_color(shadow, BOX))
    result = assigner.fit()
    assert result.team_by_track[0] == result.team_by_track[2]
    assert result.team_by_track[1] == result.team_by_track[3]
    assert result.team_by_track[0] != result.team_by_track[1]
    assert all(team is not None for team in result.team_by_track.values())


def test_grass_pixels_prevent_bright_neighbour_from_changing_illumination():
    frame = shirt_frame([100, 100, 90], .5)
    frame[:, :30] = [220, 220, 220]
    color = np.array([50., 50., 45.])
    np.testing.assert_allclose(normalize_kit_light(frame, BOX, color), color * 2)
    assert not np.allclose(normalize_kit_light(frame, BOX, color, grass_only=False), color * 2)
    np.testing.assert_array_equal(color, [50, 50, 45])


@pytest.mark.parametrize("box", [(0, 0, 80, 100), (-200, 0, -100, 80),
                                  (100, 0, 150, 80), (30, -100, 50, -50),
                                  (30, 110, 50, 180), (30, 10, 31, 12)])
def test_missing_surroundings_and_outside_boxes_do_not_wrap_image_pixels(box):
    color = np.array([100., 100., 90.])
    frame = np.full((100, 80, 3), [20, 40, 20], dtype=np.uint8)
    np.testing.assert_array_equal(normalize_kit_light(frame, box, color), color)


def test_missing_shirt_or_dark_surroundings_keeps_unknown_or_raw():
    frame = np.zeros((100, 80, 3), dtype=np.uint8)
    assert kit_color(frame, (-30, 0, -10, 80)) is None
    color = np.array([100., 100., 90.])
    np.testing.assert_array_equal(normalize_kit_light(frame, BOX, color), color)


@pytest.mark.parametrize("background,expected", [([20, 20, 20], [255, 240, 210]),
                                                 ([10, 240, 10], [50, 40, 35])])
def test_gain_and_rgb_are_bounded_even_without_green_pixels(background, expected):
    frame = np.full((100, 80, 3), background, dtype=np.uint8)
    np.testing.assert_allclose(normalize_kit_light(frame, BOX, np.array([100, 80, 70])), expected)


@pytest.mark.parametrize("normalize,expected,method", [(True, [200, 200, 180], "local_grass_v1"),
                                                      (False, [100, 100, 90], "raw_rgb_v1")])
def test_collection_uses_configured_colour_on_the_actual_tracked_box(monkeypatch, normalize, expected, method):
    from app.tracking import pipeline

    class Detections:
        def __init__(self, boxes):
            self.xyxy = np.asarray(boxes).reshape(-1, 4)
            self.confidence = np.full(len(self.xyxy), .9)
            self.tracker_id = np.ones(len(self.xyxy), dtype=int)

        def __len__(self):
            return len(self.xyxy)

        def __getitem__(self, mask):
            return Detections(self.xyxy[mask])

    tracker = SimpleNamespace(update_with_detections=lambda det: det)
    monkeypatch.setitem(sys.modules, "supervision", SimpleNamespace(ByteTrack=lambda **kw: tracker))
    monkeypatch.setattr(pipeline, "video_info", lambda _: {"fps": 25., "width": 80, "height": 100})
    frame = shirt_frame([200, 200, 180], .5)
    monkeypatch.setattr(pipeline, "iter_video_frames", lambda *a: iter([(0, 0, 0., frame), (1, 2, .08, frame)]))
    detector = SimpleNamespace(detect=lambda _: None, split=lambda _: (Detections([BOX]), Detections([])))
    calib = SimpleNamespace(image_size=(80, 100), is_on_pitch=lambda *a, **kw: True)
    cfg = pipeline.PipelineConfig(normalize_kit_light=normalize, min_track_seconds=0)
    samples, teams, stats = pipeline.collect_observations("unused.mp4", cfg, detector=detector, calib=calib, progress=False)
    assert len(samples) == 2
    assert samples[0].persons[0][1:5] == BOX
    np.testing.assert_allclose(teams._obs[1], [expected, expected])
    assert stats["kit_color_method"] == method


def test_reextraction_rejects_changed_or_missing_raw_observations():
    from scripts.soccertrack_v2.cache_local_kit_light import verify_raw_reextraction

    payload = {"samples": [{"persons": [[1]]}], "colors": {"1": [[10, 20, 30]], "99": [[0, 0, 0]]}}
    verify_raw_reextraction(payload, {"1": [[10, 20, 30]]})
    for wrong in ({}, {"1": [[10, 20, 31]]}, {"1": [[10, 20, 30]] * 2}):
        with pytest.raises(ValueError, match="raw observations differ"):
            verify_raw_reextraction(payload, wrong)
