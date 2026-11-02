"""Yayın çapası: aile ayrımı ve koni geometrisi cv2'siz, uçtan uca sentetik maske cv2 ile."""
from __future__ import annotations

import numpy as np
import pytest

from app.tracking.broadcast_anchor import (
    ImageLine,
    find_broadcast_anchor,
    line_conic_points,
    line_from_points,
    solve_pitch_to_image,
    split_families,
)
from app.tracking.calibration import dlt_homography
from app.tracking.pitch_model import model_points

SIZE = (1920, 1080)
# Elle okunmuş gerçek yayın duruşu: eğik kadraj, ızgara araması buna ulaşamıyordu.
OBLIQUE_IMAGE = [[905, 30], [1135, 123], [955, 200], [690, 312], [335, 456], [675, 152], [282, 277]]
OBLIQUE_PITCH = [[0, 0], [16.5, 13.84], [16.5, 26.69], [16.5, 41.31], [16.5, 54.16], [5.5, 24.84], [5.5, 43.16]]


def rendered_mask(h_img_to_pitch: np.ndarray) -> np.ndarray:
    pts = np.column_stack([model_points(0.1), np.ones(len(model_points(0.1)))])
    proj = pts @ np.linalg.inv(h_img_to_pitch).T
    uv = proj[:, :2] / proj[:, 2:3]
    uv = uv[(uv[:, 0] >= 1) & (uv[:, 0] < SIZE[0] - 1) & (uv[:, 1] >= 1) & (uv[:, 1] < SIZE[1] - 1)].astype(int)
    mask = np.zeros((SIZE[1], SIZE[0]), dtype=bool)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            mask[uv[:, 1] + dy, uv[:, 0] + dx] = True
    return mask


def test_families_follow_vanishing_points_not_angle_gaps():
    # Enine çizgiler yelpazelenir: açı boşluğu ortadaki çizgiyi tek başına ayırıyordu.
    apex = np.array([900.0, -600.0])
    crosswise = [line_from_points(apex + (p - apex) * 0.5, p) for p in
                 (np.array([100.0, 1000.0]), np.array([900.0, 1000.0]), np.array([1800.0, 1000.0]))]
    lengthwise = [line_from_points(np.array([0.0, y]), np.array([1900.0, y + 40.0])) for y in (200.0, 600.0)]
    first, second = split_families(crosswise + lengthwise, SIZE)
    groups = {len(first), len(second)}
    assert groups == {2, 3}
    three = first if len(first) == 3 else second
    assert all(any(ln is c for c in crosswise) for ln in three)


def test_line_conic_points_are_ordered_top_to_bottom():
    # Birim çember: x = 0 doğrusu (0, -1) ve (0, 1) noktalarında keser.
    conic = np.diag([1.0, 1.0, -1.0])
    points = line_conic_points(np.array([1.0, 0.0, 0.0]), conic)
    assert points == pytest.approx(np.array([[0.0, -1.0], [0.0, 1.0]]))
    assert line_conic_points(np.array([1.0, 0.0, -5.0]), conic) is None


def test_batch_solver_matches_general_dlt_and_marks_degenerate_as_nan():
    image = np.array(OBLIQUE_IMAGE[:4], dtype=float)
    pitch = np.array([[0.0, 0.0], [16.5, 13.84], [5.5, 24.84], [16.5, 54.16]])
    solved = solve_pitch_to_image(image[None], pitch[None])[0]
    expected = dlt_homography(pitch, image)
    assert solved / solved[2, 2] == pytest.approx(expected / expected[2, 2], rel=1e-6)
    collapsed = np.repeat(image[:1], 4, axis=0)[None]
    assert np.isnan(solve_pitch_to_image(collapsed, pitch[None])).all()


def test_image_line_angle_is_folded_to_half_circle():
    assert isinstance(line_from_points(np.zeros(2), np.array([1.0, 1.0])), ImageLine)
    assert line_from_points(np.array([1.0, 1.0]), np.zeros(2)).angle_deg == pytest.approx(45.0)


def test_finds_oblique_pose_that_grid_search_misses():
    pytest.importorskip("cv2")
    truth = dlt_homography(np.array(OBLIQUE_IMAGE, float), np.array(OBLIQUE_PITCH, float))
    res = find_broadcast_anchor(rendered_mask(truth))
    assert res.accepted, res.note
    probes = np.array([[480.0, 500.0, 1.0], [960.0, 650.0, 1.0], [1440.0, 500.0, 1.0]])
    a, b = probes @ res.homography.T, probes @ truth.T
    assert np.hypot(*((a[:, :2] / a[:, 2:3]) - (b[:, :2] / b[:, 2:3])).T).max() < 2.0


def test_empty_and_textureless_masks_return_no_homography():
    pytest.importorskip("cv2")
    res = find_broadcast_anchor(np.zeros((SIZE[1], SIZE[0]), dtype=bool))
    assert not res.accepted
    assert res.homography is None
