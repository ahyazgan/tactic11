from __future__ import annotations

import numpy as np

from app.tracking.calibration import PitchCalibration
from scripts.soccertrack_v2.correct_gsr_positions import correct_positions


def test_positions_follow_the_calibration_and_keep_other_columns() -> None:
    calib = PitchCalibration.load("data/tracking/calibrations/soccertrack_v2_117092_landmarks.json")
    u, v = calib.points[10].image
    truth = np.array(calib.points[10].pitch) - [52.5, 34.0]
    rows = np.array([[1, 7, 0, 1, u, v, truth[0] + 3.0, truth[1] - 2.0, 20.0, 40.0],
                     [1, 8, 1, 1, np.nan, np.nan, 1.0, 1.0, 20.0, 40.0]], dtype=float)
    out, summary = correct_positions(rows, calib)
    assert np.allclose(out[0, 6:8], truth, atol=0.05)          # işaret noktasında TPS tam geçer
    assert np.isnan(out[1, 6:8]).all()                          # ayak pikseli yoksa konum yok
    assert np.array_equal(out[:, :6], rows[:, :6], equal_nan=True) and np.array_equal(out[:, 8:], rows[:, 8:])
    assert summary["repositioned"] == 1 and summary["shift_vs_original_m"]["dist_median"] > 3.0
    shifted, _ = correct_positions(rows[:1], calib, v_offset=50.0)
    assert not np.allclose(shifted[0, 6:8], out[0, 6:8])
