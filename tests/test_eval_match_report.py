"""Rapor-gerçek karşılaştırma aracının bulgu uyumu hesabı."""
from __future__ import annotations

from scripts.soccertrack_v2.eval_match_report import compare, slices_of
from tests.test_tracking_match_report import AWAY, HOME, _frames


def test_identical_inputs_agree_perfectly_and_slices_follow_minutes():
    frames = _frames(0.0, 40, 10.0) + _frames(1.0, 40, 16.0) + _frames(2.0, 40, 10.0)
    assert [s[0] for s in slices_of(frames, 1.0)] == [0.0, 1.0, 2.0]
    r = compare(frames, frames, HOME, AWAY, 1.0)
    assert r["findings"]["tracked"] == r["findings"]["both"] > 0 and r["findings"]["precision"] == 1.0
    assert all(v["max"] == 0 for v in r["slice_abs_error"].values())
