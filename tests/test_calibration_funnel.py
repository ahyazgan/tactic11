"""Kalibrasyon hunisi aracı: kapı okuma, görüntüsüz kare seçimi ve toplama cv2'siz."""
from __future__ import annotations

from scripts.calibration_funnel import classify_anchor_note, pick_frames, summarize


def test_anchor_note_maps_to_first_failed_gate():
    assert classify_anchor_note("ayırt edici yapılar oturmadı (inlier %40) — çapa üretilmedi") == "landmark_inlier"
    assert classify_anchor_note("kadrajdaki çizgilerin yalnız %20'si modelle açıklanıyor") == "coverage"
    assert classify_anchor_note("TV kuralı ile kabul: yakın taç") == "accepted"
    assert classify_anchor_note("bilinmeyen not") == "other"


def test_pick_frames_skips_other_labels_and_spreads_evenly():
    picked = pick_frames(12, {0, 1, 2, 3}, 2)
    assert picked == [6, 10]
    assert pick_frames(4, {0, 1}, 6) == [2, 3]


def test_summarize_counts_line_gate_and_first_failure_per_label():
    rows = [
        {"label": "main", "grass_ratio": 0.8, "line_pixels": 900, "line_gate": True,
         "first_failed_gate": "landmark_inlier", "best_inlier": 0.5, "lm_inlier": 0.4, "lm_visible": 30, "coverage": 0.2},
        {"label": "main", "grass_ratio": 0.9, "line_pixels": 100, "line_gate": False},
        {"label": "other", "grass_ratio": 0.1, "line_pixels": 2000, "line_gate": True,
         "first_failed_gate": "accepted", "best_inlier": 0.95, "lm_inlier": 0.8, "lm_visible": 40, "coverage": 0.7},
    ]
    out = summarize(rows)
    assert out["main"]["frames"] == 2
    assert out["main"]["pass_line_gate"] == 1
    assert out["main"]["first_failed_gate"] == {"landmark_inlier": 1}
    assert out["main"]["accepted"] == 0
    assert out["other"]["accepted"] == 1
    assert out["other"]["independent_pass"]["inlier_ge090"] == 1
