"""Yayın takibi: kesmede eski duruş taşınmaz, kapıyı geçemeyen duruş üretilmez (venv-cv)."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("cv2")

from app.tracking import broadcast_track as bt  # noqa: E402
from scripts.broadcast_track_exam import evaluate, evaluate_control  # noqa: E402

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


def test_gate_gap_is_bridged_only_when_tracking_passes_again(tracker, monkeypatch):
    def refine(ratio):
        return lambda h, _d, step_px, tolerance_px: SimpleNamespace(homography=h, accepted=True, inlier_ratio=ratio)

    fill = bt.BackfillingTracker()
    fill.feed(0, textured(1))
    monkeypatch.setattr(bt, "refine_homography", refine(0.5))
    missed = fill.feed(1, textured(1)) + fill.feed(2, textured(1))
    assert all(r.homography is None for _, r in missed)
    monkeypatch.setattr(bt, "refine_homography", refine(0.9))
    results = fill.feed(3, textured(1))
    assert [(k, r.state) for k, r in results] == [(3, "tracked"), (1, "bridged"), (2, "bridged")]
    assert all(r.homography is not None for _, r in results)


def test_bridge_needs_the_flow_pose_to_close_on_the_line_pose(tracker, monkeypatch):
    fill = bt.BackfillingTracker()
    fill.feed(0, textured(1))
    monkeypatch.setattr(
        bt, "refine_homography",
        lambda h, _d, step_px, tolerance_px: SimpleNamespace(homography=h, accepted=True, inlier_ratio=0.5),
    )
    fill.feed(1, textured(1))

    def far(h, _d, step_px, tolerance_px):
        moved = h.copy()
        moved[0, 2] += bt.MAX_BRIDGE_CLOSURE_M + 1.0
        return SimpleNamespace(homography=moved, accepted=True, inlier_ratio=0.9)

    monkeypatch.setattr(bt, "refine_homography", far)
    results = fill.feed(2, textured(1))
    assert [r.state for _, r in results] == ["tracked"]
    assert fill._gap == []


def test_not_main_frames_inside_a_continuous_shot_are_bridged(tracker, monkeypatch):
    fill = bt.BackfillingTracker()
    fill.feed(0, textured(1))
    monkeypatch.setattr(bt, "classify_shot", lambda _f: SimpleNamespace(is_main=False))
    missed = fill.feed(1, textured(1))
    assert missed[0][1].state == "not_main"
    assert missed[0][1].homography is None
    monkeypatch.setattr(bt, "classify_shot", lambda _f: SimpleNamespace(is_main=True))
    results = fill.feed(2, textured(1))
    assert [(k, r.state) for k, r in results] == [(2, "tracked"), (1, "bridged")]


def test_gate_gap_is_not_bridged_when_the_pose_is_lost(tracker, monkeypatch):
    monkeypatch.setattr(
        bt, "refine_homography",
        lambda h, _d, step_px, tolerance_px: SimpleNamespace(homography=h, accepted=True, inlier_ratio=0.5),
    )
    fill = bt.BackfillingTracker()
    fill.feed(0, textured(1))
    results = []
    for k in range(1, bt.MAX_COAST_FRAMES + 2):
        results += fill.feed(k, textured(1))
    assert not [r for _, r in results if r.state == "bridged"]
    assert fill._gap == []


def gray_of(seed: int, shift: int = 0) -> np.ndarray:
    return textured(seed, shift)[:, :, 0]


def test_relocalizer_carries_pose_to_a_shifted_view(monkeypatch):
    monkeypatch.setattr(bt, "RELOC_MIN_INLIERS", 20)
    reloc = bt.Relocalizer()
    reloc.add(gray_of(1), POSE)
    located = reloc.locate(gray_of(1, shift=8))
    assert located is not None
    # Görüntüde sağa 8 px kayan nokta aynı saha konumuna düşer
    expected = POSE @ np.array([[1.0, 0.0, -8.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert np.allclose(located / located[2, 2], expected / expected[2, 2], atol=0.02)


def test_relocalizer_refuses_too_few_matches_and_unknown_views():
    reloc = bt.Relocalizer()
    assert reloc.locate(gray_of(1)) is None
    reloc.add(gray_of(1), POSE)
    assert reloc.locate(gray_of(2)) is None


def test_relocalized_chain_makes_no_keys(tracker, monkeypatch):
    track, _ = tracker
    added = []
    monkeypatch.setattr(bt, "find_broadcast_anchor",
                        lambda _m, _g: SimpleNamespace(accepted=False, homography=None, inlier=0.0))
    monkeypatch.setattr(track._reloc, "locate", lambda _g: POSE)
    monkeypatch.setattr(track._reloc, "add", lambda _g, _p: added.append(1))
    monkeypatch.setattr(bt, "RELOC_EVERY_SEARCHES", 1)
    monkeypatch.setattr(bt, "KEY_EVERY_FRAMES", 1)
    first = track.step(textured(1))
    assert first.state == "relocalized"
    assert first.origin == "reloc"
    following = track.step(textured(1, shift=2))
    assert following.state == "tracked"
    assert following.origin == "reloc"
    assert added == []


def test_evaluate_applies_development_gates():
    samples = [{"label": "main", "posed": i < 7} for i in range(10)] + [{"label": "other", "posed": False}] * 5
    record = {"match": "m", "samples": samples, "frames": 10, "produced": 7, "states": {}, "seconds": 2.0,
              "marked_frames": 3, "evidence": [{"median_m": 1.0, "state": "tracked"}, {"median_m": 1.5, "state": "tracked"},
                           {"median_m": 1.2, "state": "tracked"}]}
    result = evaluate([record])
    assert result["main_rate"] == 0.7
    assert result["D1"] and result["D2"] and result["D3"]
    assert result["D2_derived"] is False    # türetilmiş kare işaretlenmemişse doğruluğu kanıtlanmış sayılmaz
    record["evidence"].append({"median_m": 0.8, "state": "backfilled"})
    result = evaluate([record])
    assert result["D2_derived"] is True
    assert result["derived_marked_produced"] == 1
    record["evidence"].append({"median_m": 9.0, "state": "bridged"})
    result = evaluate([record])
    assert result["D2"] is False
    assert result["D2_derived"] is False


def control_record(name: str, posed: int, medians: list[float]) -> dict:
    samples = [{"label": "main", "posed": i < posed} for i in range(100)] + [{"label": "other", "posed": False}] * 10
    return {"match": name, "samples": samples, "frames": 110, "produced": posed, "states": {}, "seconds": 1.0,
            "marked_frames": len(medians),
            "evidence": [{"median_m": m, "worst_m": m + 1.0, "state": "tracked"} for m in medians]}


def test_control_passes_only_when_every_criterion_holds():
    good = [control_record("a", 60, [1.0] * 10), control_record("b", 45, [1.5] * 10)]
    result = evaluate_control(good)
    assert result["verdict"] == "GEÇTİ"
    assert all(result["gates"].values())
    assert "D1" not in result


def test_control_fails_on_a_weak_match_even_if_total_is_enough():
    result = evaluate_control([control_record("a", 80, [1.0] * 10), control_record("b", 30, [1.0] * 10)])
    assert result["main_rate"] >= 0.5
    assert result["gates"]["C1_coverage"] is False
    assert result["verdict"] == "KALDI"


def test_control_fails_on_too_little_evidence_and_on_wrong_poses():
    assert evaluate_control([control_record("a", 60, [1.0] * 14)])["gates"]["C5_minimum_sample"] is False
    wrong = evaluate_control([control_record("a", 60, [1.0] * 18 + [9.0, 9.0])])
    assert wrong["gates"]["C3_wrong_main"] is False
    assert evaluate_control([control_record("a", 60, [])])["gates"]["C2_accuracy"] is False
