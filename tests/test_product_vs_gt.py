from __future__ import annotations

import numpy as np

from scripts.soccertrack_v2 import product_vs_gt as tool


def _gt_rows(frame: int, points: np.ndarray, teams: list[int]) -> list[tuple[float, ...]]:
    return [(frame, i, teams[i], 1, 0, 0, x - 52.5, y - 34.0, 10, 20) for i, (x, y) in enumerate(points)]


def _scene(n_frames: int = 40, delta: int = 12):
    """12 oyuncu; ürün y eksenini ters görür, takım numarası terstir, bir oyuncu yanlış takımda, biri kaçmış."""
    rng = np.random.default_rng(3)
    base = np.column_stack([rng.uniform(5, 60, 12), rng.uniform(5, 63, 12)])
    teams = [0] * 6 + [1] * 6
    rows: list[tuple[float, ...]] = []
    frames = []
    for k in range(n_frames):
        seconds = 600.0 + k * 0.24
        pts = base + np.array([0.9 * k, 0.3 * np.sin(k)])
        rows += _gt_rows(round(seconds * 25) + 1 + delta, pts, teams)
        seen = pts.copy()
        seen[:, 1] = 68.0 - seen[:, 1]
        ours_team = np.array([1 - t for t in teams])
        ours_team[0] = 1 - ours_team[0]
        frames.append((seconds, seen[:11], ours_team[:11]))
    return frames, tool.gt_by_frame(np.array(rows, dtype=float))


def test_alignment_recovers_flip_delta_and_team_mapping():
    frames, gt = _scene()
    alignment = tool.learn_alignment(frames[:15], gt)
    assert (alignment["flip_x"], alignment["flip_y"]) == (False, True)
    assert alignment["delta_frames"] == 12
    assert alignment["team_crossed"] is True


def test_evaluate_reports_recall_precision_and_team_agreement():
    frames, gt = _scene()
    alignment = tool.learn_alignment(frames[:15], gt)
    result = tool.evaluate(frames[15:], gt, alignment)
    assert result["frames_evaluated"] == 25
    assert result["recall"] == round(11 / 12, 4) and result["precision"] == 1.0
    assert result["median_distance_m"] < 0.01
    assert result["team_agreement"] == round(10 / 11, 4)


def test_match_respects_the_radius_and_is_one_to_one():
    ours = np.array([[10.0, 10.0], [10.5, 10.0], [50.0, 50.0]])
    truth = np.array([[10.0, 10.0], [58.0, 50.0]])
    pairs = tool.match(ours, truth)
    assert len(pairs) == 1 and pairs[0][:2] == (0, 0)


def test_gt_by_frame_keeps_only_players_and_keepers():
    rows = np.array([(5, 0, 0, 1, 0, 0, 0.0, 0.0, 1, 1), (5, 1, -1, 3, 0, 0, 1.0, 1.0, 1, 1),
                     (5, 2, 1, 2, 0, 0, -52.5, -34.0, 1, 1)], dtype=float)
    points, teams = tool.gt_by_frame(rows)[5]
    assert points.tolist() == [[52.5, 34.0], [0.0, 0.0]] and teams.tolist() == [0, 1]
