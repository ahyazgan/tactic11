"""Tespit denetimi sınıflandırması: iyi, izdüşüm, kopya, hayalet."""
import numpy as np

from scripts.soccertrack_v2.detection_audit import classify, zone


def test_classify_separates_good_projection_duplicate_ghost() -> None:
    gt_m = np.array([[10.0, 10.0], [50.0, 30.0]])
    gt_uv = np.array([[100.0, 500.0], [900.0, 400.0]])
    feet = np.array([[101.0, 501.0],     # gt0 üstünde, sahada da yakın → iyi
                     [905.0, 402.0],     # gt1 üstünde ama sahada 8 m uzak → izdüşüm
                     [903.0, 405.0],     # gt1'e ikinci kutu → kopya
                     [2000.0, 300.0]])   # yakınında GT yok → hayalet
    det_m = np.array([[10.5, 10.0], [58.0, 30.0], [59.0, 31.0], [90.0, 5.0]])
    labels, found = classify(feet, np.full(4, 50.0), det_m, gt_m, gt_uv, np.array([True, True]))
    assert labels == ["good", "projection", "duplicate", "ghost"]
    assert found.tolist() == [True, True]


def test_gt_outside_support_is_never_used_for_image_matching() -> None:
    labels, found = classify(np.array([[100.0, 500.0]]), np.array([50.0]), np.array([[80.0, 60.0]]),
                             np.array([[10.0, 10.0]]), np.array([[100.0, 500.0]]), np.array([False]))
    assert labels == ["ghost"] and found.tolist() == [False]


def test_zone_labels() -> None:
    assert zone(5.0, 60.0) == "sol/bant3"
    assert zone(52.5, 20.0) == "orta/bant1"
    assert zone(104.9, 0.0) == "sag/bant0"
