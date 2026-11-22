"""Rapor-gerçek karşılaştırma aracının bulgu uyumu hesabı."""
from __future__ import annotations

from scripts.soccertrack_v2.eval_match_report import compare, slices_of, with_event_possession
from tests.test_tracking_match_report import AWAY, HOME, _frames


def test_identical_inputs_agree_perfectly_and_slices_follow_minutes():
    frames = _frames(0.0, 40, 10.0) + _frames(1.0, 40, 16.0) + _frames(2.0, 40, 10.0)
    assert [s[0] for s in slices_of(frames, 1.0)] == [0.0, 1.0, 2.0]
    r = compare(frames, frames, HOME, AWAY, 1.0)
    assert r["findings"]["tracked"] == r["findings"]["both"] > 0 and r["findings"]["precision"] == 1.0
    assert all(v["max"] == 0 for v in r["slice_abs_error"].values())


def test_operator_direction_reaches_both_reports_and_block_labels_are_compared():
    frames = _frames(0.0, 40, 10.0) + _frames(1.0, 40, 16.0)
    r = compare(frames, frames, HOME, AWAY, 1.0, home_attack=1)
    assert r["slice_abs_error"]["def_line_m"]["max"] == 0
    assert r["block_label_agreement"] == {"same": 4, "rate": 1.0}


def test_event_possession_rewrites_only_frames_inside_intervals():
    frames = _frames(0.0, 4, 10.0)  # 0., 1., 2., 3. saniye
    out = with_event_possession(frames, [(1.0, 3.0, 1)], HOME, AWAY)
    assert [f.possession_team_external_id for f in out] == [None, AWAY, AWAY, None]
