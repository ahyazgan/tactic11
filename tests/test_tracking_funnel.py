"""Takip hunisi aracı: kayıp sınıflaması, toplama ve el noktası hatası cv2'siz."""
from __future__ import annotations

import numpy as np

from scripts.tracking_funnel import VARIANTS, classify_loss, is_cut, mark_errors, summarize


def test_cut_needs_lost_flow_or_changed_picture():
    assert is_cut(10, 1.0)
    assert is_cut(200, 0.5)
    # Az nokta oranı kesme değildir: geliştirmede oran 0,3 altı karelerin görüntüsü aynıydı
    assert not is_cut(60, 1.0)


def test_loss_blames_lines_only_when_true_pose_has_no_lines():
    assert classify_loss(cut=True, reference_inlier=0.99, produced=False) == "cut"
    assert classify_loss(cut=False, reference_inlier=0.99, produced=True) == "produced"
    assert classify_loss(cut=False, reference_inlier=0.40, produced=False) == "line_extraction"
    assert classify_loss(cut=False, reference_inlier=0.90, produced=False) == "search"
    assert classify_loss(cut=False, reference_inlier=0.75, produced=False, gate=0.70) == "search"


def test_mark_errors_measure_metres_at_the_marked_points():
    pose = np.array([[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 1.0]])
    points = [{"image": [100, 100], "pitch": [10, 10]}, {"image": [200, 100], "pitch": [20, 13]}]
    assert np.allclose(mark_errors(pose, points), [0.0, 3.0])


def test_summarize_skips_anchor_frame_and_counts_each_variant():
    def row(k: int, ok: bool) -> dict:
        state = {"ok": ok, "inlier": 0.9, "dev_m": 1.0 if k else 0.0}
        return {"k": k, "cut": False, "main": True, "ref_inlier_prod": 0.3, "ref_inlier_day": 0.9,
                **{name: state for name in VARIANTS}}

    clip = {"closure_m": 0.5, "rows": [row(0, True), row(1, True), row(2, False)]}
    result = summarize([clip])
    assert result["frames"] == 2
    assert result["variants"]["day_flow_070"]["losses"] == {"produced": 1, "search": 1}
    assert result["variants"]["prod_prev_085"]["losses"] == {"produced": 1, "line_extraction": 1}
    assert result["variants"]["day_flow_070"]["deviation_from_reference_m"]["median"] == 1.0
