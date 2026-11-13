from __future__ import annotations

from collections import Counter

import numpy as np

from scripts.soccertrack_v2 import team_color_spot_check as check


def _pixels(hsv: tuple[int, int, int], n: int) -> np.ndarray:
    return np.tile(np.array(hsv, dtype=np.uint8), (n, 1))


def test_kit_label_needs_a_dominant_kit_colour():
    grass, blue, white = (60, 200, 120), (110, 200, 200), (0, 10, 240)
    height = 100.0  # gövde alanı 910 piksel, eşik 455
    assert check.kit_label(np.vstack([_pixels(grass, 3000), _pixels(blue, 600)]), height) == "blue"
    assert check.kit_label(np.vstack([_pixels(grass, 3000), _pixels(white, 600)]), height) == "white"
    assert check.kit_label(np.vstack([_pixels(blue, 600), _pixels(white, 600)]), height) is None
    assert check.kit_label(_pixels(grass, 3000), height) is None


def test_player_height_grows_toward_the_camera():
    assert check.player_height_px(100) == check.FAR_HEIGHT_PX
    assert check.player_height_px(800) > check.player_height_px(400) > check.FAR_HEIGHT_PX


def test_agreement_picks_the_better_team_to_kit_mapping():
    pairs = Counter({("home", "blue"): 30, ("away", "white"): 50, ("home", "white"): 15, ("away", "blue"): 5})
    assert check.agreement(pairs) == {"labelled": 100, "agree": 80, "agreement": 0.8, "home_kit": "blue"}
    assert check.agreement(Counter())["agreement"] is None
