"""Kare sahipliği ve top kaybı ölçüm aracının hesapları."""
from __future__ import annotations

from scripts.soccertrack_v2.eval_frame_possession import frame_turnovers, match_times, score


def _f(sec: float, owner: int | None) -> dict:
    return {"minute": sec / 60.0, "possession_team_external_id": owner}


def test_score_counts_coverage_and_accuracy_inside_intervals_only():
    frames = [_f(0.5, 1), _f(1.5, None), _f(2.5, 2), _f(9.0, 1)]
    r = score(frames, [(0.0, 3.0, 0)], home=1, away=2)
    assert (r["in_possession"], r["labelled"], r["correct"]) == (3, 2, 1)
    assert r["coverage"] == 0.667 and r["accuracy"] == 0.5


def test_frame_turnovers_skip_empty_frames_but_not_long_gaps():
    frames = [_f(0, 1), _f(1, None), _f(2, 2), _f(10, 1)]
    assert frame_turnovers(frames) == [2.0]


def test_match_times_is_one_to_one_within_tolerance():
    r = match_times([1.0, 1.5, 9.0], [1.2, 20.0])
    assert (r["matched"], r["precision"], r["recall"]) == (1, 0.333, 0.5)
