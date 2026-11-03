"""Kapsama tanı aracı: durum eşlemesi, çekim dizisi boyu ve dilim oranları cv2'siz."""
from __future__ import annotations

from scripts.coverage_diagnosis import arm_counts, reason_of, run_lengths, tercile_rates


def test_reason_groups_states_and_keeps_posed_apart():
    assert reason_of("searching") == reason_of("no_anchor") == "anchor_missing"
    assert reason_of("gate") == "line_gate_rejected"
    assert reason_of("gate_lost") == reason_of("not_main_lost") == "tracking_lost"
    assert reason_of("tracked") == reason_of("backfilled") == "posed"


def test_run_lengths_count_consecutive_main_samples_only():
    labels = ["main", "main", "other", "main", "other", "other", "main", "main", "main"]
    assert run_lengths(labels) == [2, 2, 0, 1, 0, 0, 3, 3, 3]
    assert run_lengths([]) == []


def test_tercile_rates_split_values_and_report_coverage():
    rows = tercile_rates([1, 2, 3, 4, 5, 6], [False, False, False, True, True, True])
    assert [r["n"] for r in rows] == [2, 2, 2]
    assert [r["rate"] for r in rows] == [0.0, 0.5, 1.0]


def test_arm_counts_separates_main_coverage_loss_and_other_leak():
    samples = [
        {"label": "main", "posed": True, "state": "tracked"},
        {"label": "main", "posed": False, "state": "searching"},
        {"label": "main", "posed": False, "state": "not_main"},
        {"label": "other", "posed": True, "state": "tracked"},
        {"label": "other", "posed": False, "state": "replay"},
    ]
    assert arm_counts(samples) == {"main_posed": 1, "main_n": 3, "other_posed": 1, "other_n": 2,
                                   "lost": {"anchor_missing": 1, "shot_filter": 1}}
