import numpy as np
import pytest

from app.tracking.calibration import CalibrationError, PitchCalibration
from app.tracking.pipeline import validate_video_calibration
from scripts.soccertrack_v2.calibration_from_keypoints import from_keypoints


def landmarks():
    return {f"({x},{y})": [100 + x * 10, 50 + y * 10]
            for x in (0, 26, 52, 78, 105) for y in (0, 34, 68)}


def test_landmark_conversion_uses_physical_points_and_serializes():
    cal = from_keypoints(landmarks(), (1300, 800))
    assert cal.method == "tps" and len(cal.points) == 15
    assert np.allclose(cal.image_to_pitch_m(600, 400), [50, 35])
    loaded = PitchCalibration.from_dict(cal.to_dict())
    assert loaded.meta["source"] == cal.meta["source"]
    assert np.allclose(loaded.image_to_pitch_m(600, 400), [50, 35])


@pytest.mark.parametrize("label,pixel", [("(106,0)", [10, 20]), ("(2,3,4)", [10, 20]),
                                      ("(0,0)", [-1, 4]), ("(0,0)", [1400, 0])])
def test_invalid_landmarks_are_rejected(label, pixel):
    with pytest.raises(ValueError):
        from_keypoints({**landmarks(), label: pixel}, (1300, 800))


def test_video_dimensions_must_match_calibrated_pixel_space():
    cal = from_keypoints(landmarks(), (1300, 800))
    validate_video_calibration({"width": 1300, "height": 800}, cal)
    validate_video_calibration({"width": 1920, "height": 1080}, None)
    with pytest.raises(CalibrationError, match="yeniden oluşturun"):
        validate_video_calibration({"width": 1920, "height": 1080}, cal)
