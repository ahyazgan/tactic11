from __future__ import annotations

import numpy as np

from scripts.soccertrack_v2 import physical_load_vs_gt as tool


def test_gt_tracks_keep_players_with_positions_in_pitch_metres():
    rows = np.array([(25, 7, 0, 1, 0, 0, 0.0, 0.0, 1, 1), (50, 7, 0, 1, 0, 0, 2.0, 0.0, 1, 1),
                     (25, 8, -1, 3, 0, 0, 1.0, 1.0, 1, 1), (25, 9, 1, 2, 0, 0, np.nan, 0.0, 1, 1)], dtype=float)
    assert tool.gt_tracks(rows) == {7: [(1.0, 52.5, 34.0, None), (2.0, 54.5, 34.0, None)]}


def test_compare_applies_each_gate_separately():
    truth = {"m_per_player_min": 120.0, "hsr_share": 0.03, "sprint_share": 0.008}
    close = tool.compare({"m_per_player_min": 110.0, "hsr_share": 0.04, "sprint_share": 0.01}, truth)
    assert close["passed"] and close["m_per_player_min_relative_error"] == round(110 / 120 - 1, 4)
    far = tool.compare({"m_per_player_min": 140.0, "hsr_share": 0.05, "sprint_share": 0.008}, truth)
    assert far["checks"] == {"m_per_player_min": False, "hsr_share": False, "sprint_share": True}
