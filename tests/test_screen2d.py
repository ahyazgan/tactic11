"""2D üstten görünüm ayrıştırıcısı: sentetik FM benzeri karede saha, daire, top, takım."""

from __future__ import annotations

import numpy as np

from app.tracking.screen2d import PitchRect, TeamPalette, detect, find_pitch, label, nearest_owner

RED, BLUE, WHITE = (210, 40, 40), (40, 70, 200), (245, 245, 245)
X0, Y0, PW, PH = 40, 30, 630, 408   # saha dikdörtgeni (105×68 oranı)


def _disc(img: np.ndarray, cx: float, cy: float, r: float, color: tuple[int, int, int]) -> None:
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    d = np.hypot(xx - cx, yy - cy)
    img[d <= r + 1] = (20, 20, 20)        # koyu dış çizgi
    img[d <= r] = color


def _px(x_pct: float, y_pct: float) -> tuple[float, float]:
    return X0 + x_pct / 100 * PW, Y0 + y_pct / 100 * PH


def scene(ball: tuple[float, float] | None = (70.0, 50.0)) -> tuple[np.ndarray, list[tuple[int, float, float]]]:
    img = np.full((PH + 2 * Y0, PW + 2 * X0, 3), (60, 60, 60), dtype=np.uint8)
    img[Y0:Y0 + PH, X0:X0 + PW] = (50, 140, 60)
    img[Y0:Y0 + 2, X0:X0 + PW] = WHITE                               # üst taç
    img[Y0 + PH - 2:Y0 + PH, X0:X0 + PW] = WHITE
    img[Y0:Y0 + PH, X0 + PW // 2 - 1:X0 + PW // 2 + 1] = WHITE       # orta çizgi
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    ring = np.abs(np.hypot(xx - (X0 + PW / 2), yy - (Y0 + PH / 2)) - 55) <= 1
    img[ring] = WHITE
    truth = []
    for i in range(10):
        hx, hy = 15 + 6 * (i % 5), 15 + 17 * (i // 5) + 3 * i
        ax, ay = 52 + 7 * (i % 5), 20 + 15 * (i // 5) + 4 * i
        truth += [(0, hx, hy), (1, ax, ay)]
    truth.append((0, 50.0, 30.0))   # orta çizginin üstündeki daire (çizgiyle birleşmemeli)
    for team, x, y in truth:
        _disc(img, *_px(x, y), 8, RED if team == 0 else BLUE)
    if ball is not None:
        _disc(img, *_px(*ball), 3, WHITE)
    return img, truth


def test_find_pitch_returns_the_green_rectangle() -> None:
    img, _ = scene()
    rect = find_pitch(img)
    assert rect is not None
    assert abs(rect.x0 - X0) <= 2 and abs(rect.x1 - (X0 + PW)) <= 2
    assert abs(rect.y0 - Y0) <= 3 and abs(rect.y1 - (Y0 + PH)) <= 3


def test_detects_all_discs_with_teams_and_positions() -> None:
    img, truth = scene()
    palette = TeamPalette(home_hint=RED)
    det = detect(img, palette)
    assert det is not None and len(det.players) == len(truth)
    for team, x, y in truth:
        got = min(det.players, key=lambda p: np.hypot(p[1] - x, p[2] - y))
        assert np.hypot(got[1] - x, got[2] - y) < 1.0
        assert got[0] == team


def test_ball_found_and_owner_from_nearest_player() -> None:
    img, _ = scene(ball=(51.5, 31.5))   # orta çizgideki kırmızı oyuncunun dibinde
    det = detect(img, TeamPalette(home_hint=RED))
    assert det is not None and det.ball is not None
    assert abs(det.ball[0] - 51.5) < 1 and abs(det.ball[1] - 31.5) < 1.5
    assert nearest_owner(det) == 0
    img2, _ = scene(ball=None)
    det2 = detect(img2, TeamPalette(home_hint=RED))
    assert det2 is not None and det2.ball is None and nearest_owner(det2) is None


def test_palette_swap_and_outlier_colour() -> None:
    img, _ = scene()
    p = TeamPalette(home_hint=RED, swap=True)
    det = detect(img, p)
    assert det is not None
    reds = [t for t, x, y in det.players if x < 45]
    assert set(reds) == {1}
    from app.tracking.screen2d import Blob
    assert p.assign(Blob(0, 0, 50, (240, 230, 20))) is None   # sarı kaleci: takıma atanmaz


def test_label_components_and_to_pct() -> None:
    m = np.zeros((6, 6), dtype=bool)
    m[0:2, 0:2] = True
    m[4:6, 3:6] = True
    assert sorted(len(c) for c in label(m)) == [4, 6]
    rect = PitchRect(10, 10, 110, 60)
    assert rect.to_pct(60, 35) == (50.0, 50.0)
    assert rect.to_pct(0, 100) == (0.0, 100.0)
