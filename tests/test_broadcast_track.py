"""Yayın takibi: kesmede eski duruş taşınmaz, kapıyı geçemeyen duruş üretilmez (venv-cv)."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("cv2")

from app.tracking import broadcast_track as bt  # noqa: E402
from scripts.broadcast_track_exam import evaluate  # noqa: E402

POSE = np.array([[0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 1.0]])


def textured(seed: int, shift: int = 0, level: int = 200) -> np.ndarray:
    import cv2

    noise = np.random.default_rng(seed).integers(0, level, (360, 640), dtype=np.uint8)
    gray = cv2.GaussianBlur(noise, (5, 5), 0)
    return cv2.cvtColor(np.roll(gray, shift, axis=1), cv2.COLOR_GRAY2BGR)


@pytest.fixture
def tracker(monkeypatch):
    searches = []

    def anchor(_mask, _gray):
        searches.append(1)
        return SimpleNamespace(accepted=True, homography=POSE, inlier=0.9)

    monkeypatch.setattr(bt, "find_broadcast_anchor", anchor)
    monkeypatch.setattr(bt, "daylight_line_mask", lambda f: np.zeros(f.shape[:2], dtype=bool))
    monkeypatch.setattr(bt, "classify_shot", lambda _f: SimpleNamespace(is_main=True))
    monkeypatch.setattr(bt, "red_ratio", lambda _f: 0.0)
    monkeypatch.setattr(
        bt, "refine_homography",
        lambda h, _d, step_px, tolerance_px: SimpleNamespace(homography=h, accepted=True, inlier_ratio=0.9),
    )
    return bt.BroadcastTracker(), searches


def test_first_frame_anchors_and_next_frame_tracks(tracker):
    track, searches = tracker
    assert track.step(textured(1)).state == "anchored"
    next_frame = track.step(textured(1, shift=2))
    assert next_frame.state == "tracked"
    assert next_frame.homography is not None
    assert len(searches) == 1


def test_cut_drops_pose_and_next_frame_searches_again(tracker):
    track, searches = tracker
    track.step(textured(1))
    black = np.zeros((360, 640, 3), dtype=np.uint8)
    cut = track.step(black)
    assert cut.state == "cut"
    assert cut.homography is None
    assert track._h is None
    assert track.step(textured(2)).state == "cut"   # karadan görüntüye dönüş de kesmedir
    assert track.step(textured(2)).state == "anchored"
    assert len(searches) == 2


def test_gate_failure_gives_no_pose_and_gives_up_after_coast_limit(tracker, monkeypatch):
    track, _ = tracker
    track.step(textured(1))
    monkeypatch.setattr(
        bt, "refine_homography",
        lambda h, _d, step_px, tolerance_px: SimpleNamespace(homography=h, accepted=True, inlier_ratio=0.5),
    )
    states = [track.step(textured(1)) for _ in range(bt.MAX_COAST_FRAMES + 1)]
    assert all(s.homography is None for s in states)
    assert states[0].state == "gate"
    assert states[-1].state == "gate_lost"
    assert track._h is None


def test_large_correction_is_rejected(tracker, monkeypatch):
    track, _ = tracker
    track.step(textured(1))
    far = POSE.copy()
    far[0, 2] = bt.MAX_JUMP_M + 1.0
    monkeypatch.setattr(
        bt, "refine_homography",
        lambda _h, _d, step_px, tolerance_px: SimpleNamespace(homography=far, accepted=True, inlier_ratio=0.95),
    )
    assert track.step(textured(1)).state == "gate"


def test_replay_drops_pose_without_searching(tracker, monkeypatch):
    track, searches = tracker
    track.step(textured(1))
    monkeypatch.setattr(track._replay, "update", lambda _t, _r: True)
    for _ in range(3):
        result = track.step(textured(1))
    assert result.state == "replay"
    assert result.homography is None
    assert len(searches) == 1


def test_backfill_walks_back_to_the_frames_waiting_for_an_anchor(tracker, monkeypatch):
    calls = []

    def anchor(_mask, _gray):
        calls.append(1)
        accepted = len(calls) >= 2
        return SimpleNamespace(accepted=accepted, homography=POSE if accepted else None, inlier=0.9)

    monkeypatch.setattr(bt, "find_broadcast_anchor", anchor)
    fill = bt.BackfillingTracker()
    results = []
    for k in range(bt.ANCHOR_EVERY_FRAMES + 1):
        results += fill.feed(k, textured(1, shift=k))
    filled = [k for k, r in results if r.state == "backfilled"]
    assert filled == list(range(bt.ANCHOR_EVERY_FRAMES - 1, -1, -1))
    assert all(r.homography is not None for _, r in results if r.state == "backfilled")


def test_backfill_stops_at_a_cut(tracker, monkeypatch):
    calls = []

    def anchor(_mask, _gray):
        calls.append(1)
        accepted = len(calls) >= 3
        return SimpleNamespace(accepted=accepted, homography=POSE if accepted else None, inlier=0.9)

    monkeypatch.setattr(bt, "find_broadcast_anchor", anchor)
    fill = bt.BackfillingTracker()
    results = []
    for k in range(3):
        results += fill.feed(k, textured(1, shift=k))
    results += fill.feed(3, np.zeros((360, 640, 3), dtype=np.uint8))
    for k in range(4, 4 + 2 * bt.ANCHOR_EVERY_FRAMES + 1):
        results += fill.feed(k, textured(2, shift=k))
    filled = [k for k, r in results if r.state == "backfilled"]
    assert filled
    assert min(filled) >= 4


def test_evaluate_applies_development_gates():
    samples = [{"label": "main", "posed": i < 7} for i in range(10)] + [{"label": "other", "posed": False}] * 5
    record = {"match": "m", "samples": samples, "frames": 10, "produced": 7, "states": {}, "seconds": 2.0,
              "marked_frames": 3, "evidence": [{"median_m": 1.0}, {"median_m": 1.5}, {"median_m": 1.2}]}
    result = evaluate([record])
    assert result["main_rate"] == 0.7
    assert result["D1"] and result["D2"] and result["D3"]
    record["evidence"].append({"median_m": 9.0})
    assert evaluate([record])["D2"] is False
