"""Diagnostic counts must not turn ambiguous spatial matches into true identities."""
from __future__ import annotations

import numpy as np

from scripts.soccertrack_v2.audit_team_errors import collect_records, summarize
from scripts.soccertrack_v2.render_team_error_review import review_samples


def observation(segment=0, track=1, predicted=0, gt_team=1, gt_track=10, **extra):
    return {"segment": segment, "track": track, "predicted_team": predicted,
            "gt_team": gt_team, "gt_track": gt_track, "seconds": 600.0,
            "opposite_gt_in_radius": False, "nearest_gt": True, "distance_m": 2.0, **extra}


def test_track_ids_are_scoped_to_the_segment():
    report = summarize([observation(), observation(segment=3, gt_team=0, gt_track=20)])
    assert report["wrong"] == 1
    assert report["wrong_on_track_with_multiple_gt_ids"] == 0
    assert report["wrong_on_track_with_multiple_gt_teams"] == 0


def test_warning_flags_overlap_without_double_counting_mismatches():
    rows = [observation(opposite_gt_in_radius=True, nearest_gt=False, distance_m=1.0),
            observation(gt_team=0, gt_track=20, seconds=600.8),
            observation(track=2, predicted=None)]
    report = summarize(rows)
    assert (report["matched"], report["assigned"], report["correct"], report["wrong"], report["unassigned"]) == (3, 2, 1, 1, 1)
    for key in ("wrong_with_opposite_gt_in_radius", "wrong_on_track_with_multiple_gt_teams",
                "wrong_on_track_with_multiple_gt_ids", "wrong_not_nearest_gt", "wrong_within_1_5m"):
        assert report[key] == 1
    assert len(report["ranked_error_tracks"]) == 1
    assert report["ranked_error_tracks"][0]["matched"] == 2


def test_empty_audit_does_not_invent_accuracy_or_errors():
    report = summarize([])
    assert report["matched"] == report["assigned"] == report["wrong"] == 0
    assert report["ranked_error_tracks"] == []


def test_review_deduplicates_frames_and_keeps_agreement_for_comparison():
    rows = [observation(), observation(gt_team=0, seconds=600.8),
            observation(segment=3, gt_team=0, seconds=690.0)]
    report = {"records": rows, "splits": {"development": summarize(rows)}}
    selected = review_samples(report, "development", 6)
    assert [[r["seconds"] for r in g] for g in selected] == [[600.0, 600.8]]


def test_collection_preserves_frozen_alignment_and_ambiguous_alternatives():
    # Two equally plausible opposing players: expose ambiguity, do not select
    # a GT team using the predicted shirt colour. The third label is a keeper.
    payload = {"segment": 0, "video": "test.mp4", "colors": {"1": [[220, 30, 30]] * 2,
               "2": [[30, 40, 220]] * 2}, "samples": [{"persons": [[1], [2]]}]}
    samples = [(600.0, [[1, 0, 0, 10, 20]], np.array([[52.5, 34.0]]))]
    gt = {15010: np.array([[15010, 10, 0, 1, 0, 0, 0.5, 0, 1, 1],
                          [15010, 20, 1, 1, 0, 0, -0.5, 0, 1, 1],
                          [15010, 30, 1, 2, 0, 0, 10, 0, 1, 1]])}
    rows = collect_records([(payload, samples)], gt, {"fps": 25, "delta_frames": 9}, 3.0)
    assert len(rows) == 1
    assert rows[0]["gt_frame"] == 15010
    assert rows[0]["opposite_gt_in_radius"] is True
    assert rows[0]["distance_m"] == 0.5
    assert rows[0]["video_seconds"] == 0.0
    assert collect_records([(payload, samples)], gt, {"fps": 25, "delta_frames": 0}, 3.0) == []
