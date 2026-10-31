"""Çapalı takım ataması deneyi: sınıflandırma, aykırılık ve kayma koruması."""
import numpy as np

from scripts.soccertrack_v2.anchored_team_experiment import (
    assign,
    classify,
    classify_chroma,
    seeded_centers,
    summary,
)

WHITE, BLUE = np.array([220.0, 220.0, 225.0]), np.array([40.0, 60.0, 170.0])
ANCHOR = np.vstack([WHITE, BLUE])


def shaded_scene() -> np.ndarray:
    # üretimdeki k=2 bu üç grubu "aydınlık beyaz" / "gölge beyaz + mavi" diye bölebilir
    lit = WHITE + np.random.default_rng(0).normal(0, 4, (6, 3))
    shade = np.array([150.0, 150.0, 160.0]) + np.random.default_rng(1).normal(0, 4, (6, 3))
    blue = BLUE + np.random.default_rng(2).normal(0, 4, (6, 3))
    return np.vstack([lit, shade, blue])


def test_rgb_anchor_never_gives_shadowed_white_to_blue() -> None:
    labels = classify(shaded_scene(), ANCHOR)
    assert labels[:6].tolist() == [0] * 6
    assert labels[12:].tolist() == [1] * 6
    assert 1 not in labels[6:12].tolist()          # gölge: atanmamış kalır (RGB'de çapadan uzak)


def test_chroma_anchor_keeps_shadowed_white_with_white_team() -> None:
    labels = classify_chroma(shaded_scene(), ANCHOR)
    assert labels.tolist() == [0] * 12 + [1] * 6


def test_classify_rejects_other_colours() -> None:
    feats = np.vstack([WHITE, WHITE + 3, BLUE, BLUE - 3, [200.0, 30.0, 30.0]])  # kırmızı: hakem/kaleci
    assert classify(feats, ANCHOR).tolist()[-1] == -1


def test_seeded_centers_follow_lighting_shift() -> None:
    feats = np.vstack([np.tile(WHITE - 30, (5, 1)), np.tile(BLUE - 15, (5, 1))])
    moved = seeded_centers(feats, ANCHOR)
    assert np.allclose(moved, [WHITE - 30, BLUE - 15])


def test_seeded_falls_back_when_drift_is_large() -> None:
    payload = {"colors": {str(t): [c.tolist(), c.tolist()] for t, c in
                          enumerate([WHITE - 90, WHITE - 92, BLUE, BLUE + 1])},
               "samples": [{"persons": [[t, 0, 0, 1, 1, 1.0] for t in range(4)]}]}
    _teams, used = assign("seeded", payload, ANCHOR, max_drift=40.0)
    assert used == "nearest_anchor"
    _teams, used = assign("seeded", payload, ANCHOR, max_drift=200.0)
    assert used == "seeded"


def test_summary_maps_home_to_gt_team() -> None:
    pairs = [(0, 1), (1, 0), (0, 0), (None, 1)]
    s = summary(pairs, home_gt=1)
    assert (s["assigned"], s["correct"], s["unassigned_ratio"]) == (3, 2, 0.25)


def _payload(colors: list[np.ndarray]) -> dict:
    return {"colors": {str(t): [c.tolist(), (c + 1).tolist(), (c - 1).tolist()] for t, c in enumerate(colors)},
            "samples": [{"persons": [[t, 0, 0, 1, 1, 1.0] for t in range(len(colors))]}]}


def test_gated_anchor_keeps_production_when_clusters_match_anchor() -> None:
    payload = _payload([WHITE + d for d in (-4, 0, 4)] + [BLUE + d for d in (-4, 0, 4)])
    _teams, used = assign("gated_anchor", payload, ANCHOR, max_drift=40.0)
    assert used == "production"


def test_gated_anchor_switches_when_clustering_splits_by_light() -> None:
    # aydınlık beyaz / gölge beyaz + mavi: üretim merkezlerinden biri çapadan çok uzak
    lit = [WHITE + d for d in (-3, 0, 3, 5)]
    shade = [np.array([120.0, 125.0, 150.0]) + d for d in (-3, 0, 3)]
    blue = [BLUE + d for d in (-3, 0, 3)]
    teams, used = assign("gated_anchor", _payload(lit + shade + blue), ANCHOR, max_drift=40.0)
    assert used == "nearest_anchor"
    assert [teams[t] for t in range(4)] == [0] * 4
    assert [teams[t] for t in range(7, 10)] == [1] * 3
