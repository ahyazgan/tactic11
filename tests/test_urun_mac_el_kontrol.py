"""El kontrol sayfası: örnek kare seçimi, saha→görüntü geri düşürme ve ön kayıtlı hüküm."""
from __future__ import annotations

import pytest

from app.tracking.calibration import PitchCalibration
from scripts import urun_mac_el_kontrol as review

CALIB = PitchCalibration.from_dict({
    "image_size": [1050, 680],
    "points": [{"image": [0, 0], "pitch": [0, 0]}, {"image": [1050, 0], "pitch": [105, 0]},
               {"image": [1050, 680], "pitch": [105, 68]}, {"image": [0, 680], "pitch": [0, 68]}],
})
FRAMES = [{"minute": 0.5, "players": [{}] * 20}, {"minute": 3.0, "players": [{}] * 18}, {"minute": None}]


def test_nearest_frame_picks_the_closest_minute_and_ignores_frames_without_one():
    assert review.nearest_frame(FRAMES, 2.4)["minute"] == 3.0
    assert review.nearest_frame(FRAMES, 0.0)["minute"] == 0.5
    with pytest.raises(ValueError, match="dakikası olan kare yok"):
        review.nearest_frame([{"minute": None}], 1.0)


def test_inverse_lookup_returns_the_pixel_within_one_grid_step():
    lookup = review.inverse_lookup(CALIB, step=10)
    at = lookup(50.0, 50.0)  # saha ortası → görüntü ortası
    assert at is not None and abs(at[0] - 525) <= 10 and abs(at[1] - 340) <= 10
    corner = lookup(0.0, 0.0)
    assert corner is not None and corner[0] <= 10 and corner[1] <= 10


def test_inverse_lookup_refuses_positions_outside_the_image():
    assert review.inverse_lookup(CALIB, step=10)(180.0, 50.0) is None


def test_sheet_rows_follow_the_registered_sample_and_leave_the_hand_fields_empty():
    rows = review.sheet_rows({"review_minutes": [0.4, 2.9]}, FRAMES)
    assert [(r["n"], r["minute"], r["predicted_players"]) for r in rows] == [(1, 0.5, 20), (2, 3.0, 18)]
    assert all(r["hand_count"] is None and r["ghosts"] is None for r in rows)
    assert review.sheet_rows({}, FRAMES) == []


def test_verdict_waits_for_every_row_and_then_applies_both_gates():
    rows = [{"hand_count": 20, "predictions_on_a_person": 16, "ghosts": 2},
            {"hand_count": 20, "predictions_on_a_person": None, "ghosts": 1}]
    assert review.review_verdict(rows, 0.7, 0.2) == {"complete": False}
    rows[1]["predictions_on_a_person"] = 14
    verdict = review.review_verdict(rows, 0.7, 0.2)
    assert verdict == {"complete": True, "recall": 0.75, "ghost_share": round(3 / 33, 4), "passed": True}
    rows[1]["ghosts"] = 12
    assert review.review_verdict(rows, 0.7, 0.2)["passed"] is False
    assert review.review_verdict([], 0.7, 0.2) == {"complete": False}


def test_frame_command_seeks_before_input_for_frame_accuracy():
    from pathlib import Path

    cmd = review.frame_command("ffmpeg", "mac.mp4", 107.28, Path("01_ham.jpg"))
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "107.280"
    assert cmd[-1] == "01_ham.jpg"
