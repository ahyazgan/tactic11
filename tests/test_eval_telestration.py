"""Telestrasyon doğruluk ölçümü: hizalama, takım eşlemesi, yön ve özet ölçütleri."""
from collections import Counter

import numpy as np

from scripts.soccertrack_v2.eval_telestration import (
    Record,
    gt_attack_direction,
    gt_frame,
    gt_index,
    home_gt_team,
    match,
    summarise,
)


def test_gt_frame_uses_absolute_seconds_and_delta() -> None:
    assert gt_frame(10.0, 9) == 15010          # 600 sn · 25 + 1 + 9
    assert gt_frame(10.0 + 0.24 / 60, 9) == 15016


def test_gt_index_keeps_players_and_keepers_with_positions() -> None:
    rows = np.array([[1, 1, 0, 1, 0, 0, 1.0, 2.0, 0, 0],
                     [1, 2, 1, 2, 0, 0, 3.0, 4.0, 0, 0],
                     [1, 3, -1, 3, 0, 0, 5.0, 6.0, 0, 0],      # başka kategori
                     [2, 4, 0, 1, 0, 0, np.nan, 1.0, 0, 0]])   # konumsuz
    index = gt_index(rows)
    assert list(index) == [1]
    assert index[1][:, 1].tolist() == [1, 2]


def test_match_respects_radius() -> None:
    pred = np.array([[0.0, 0.0], [10.0, 0.0]])
    gt = np.array([[10.5, 0.0], [50.0, 50.0]])
    assert match(pred, gt) == [(1, 0)]


def test_home_team_mapping_by_majority() -> None:
    assert home_gt_team(Counter({(0, 0): 40, (1, 1): 35, (0, 1): 10})) == 0
    assert home_gt_team(Counter({(0, 1): 40, (1, 0): 35, (0, 0): 10})) == 1


def test_attack_direction_from_keepers() -> None:
    # GT takım 0 kalecisi solda (x<0): x+ yönüne hücum eder
    g = np.array([[5, 1, 0, 2, 0, 0, -48.0, 0.0, 0, 0], [5, 2, 1, 2, 0, 0, 47.0, 0.0, 0, 0]])
    gt = {5: g}
    assert gt_attack_direction(gt, [5], 0) == 1
    assert gt_attack_direction(gt, [5], 1) == -1
    assert gt_attack_direction({}, [5], 0) == 0


def test_summary_reports_baseline_and_balanced_accuracy() -> None:
    hi, mid = "Yüksek blok", "Orta blok"
    ref = [Record("drawn", hi, [(50.0, 0, 1)])] * 8 + [Record("drawn", mid, [(40.0, 0, 1)])] * 2
    test = [Record("drawn", hi, [(52.0, 0, 1)])] * 10   # hep baskın sınıfı söyleyen tahmin
    s = summarise(ref, test)
    assert s["block_match_pct"] == 80.0
    assert s["majority_baseline_pct"] == 80.0
    assert s["block_balanced_pct"] == 50.0             # sabit tahmin dengeli doğrulukta ödüllenmez
    assert s["def_line_error"]["median_m"] == 2.0
    assert s["block_confusion"] == {f"{hi} -> {hi}": 8, f"{mid} -> {hi}": 2}


def test_summary_counts_frames_drawn_by_one_side_only() -> None:
    ref = [Record("drawn", "Orta blok"), Record("players", None)]
    test = [Record("players", None), Record("drawn", "Orta blok")]
    s = summarise(ref, test)
    assert (s["drawn_both"], s["ref_only"], s["test_only"]) == (0, 1, 1)
    assert s["label_exact_pct"] is None
