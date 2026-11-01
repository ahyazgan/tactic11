"""Otomatik telestrasyon: izdüşüm, blok çizgileri, faz etiketi ve kapılar."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.domain import TrackingFrame
from app.domain.tracking import PlayerPosition
from app.tracking.calibration import CalibrationPoint, PitchCalibration
from app.tracking.telestration import (
    Line,
    PlayerSpot,
    Telestrator,
    _convex_hull,
    _Projector,
    block_label,
    render,
    spots_from_frame,
)

# saha metresi → görüntü pikseli (hafif perspektif)
G = np.array([[16.0, 2.0, 100.0], [0.0, 9.0, 150.0], [0.0, 0.004, 1.0]])


def img(x: float, y: float) -> tuple[float, float]:
    q = G @ np.array([x, y, 1.0])
    return float(q[0] / q[2]), float(q[1] / q[2])


def calib(noise: float = 0.0) -> PitchCalibration:
    rng = np.random.default_rng(1)
    pts = []
    # saha işaretleri üzerindeki noktalar (taç/kale çizgisi, ceza sahası, orta çizgi)
    for x in (0.0, 16.5, 52.5, 88.5, 105.0):
        for y in (0.0, 13.84, 34.0, 54.16, 68.0):
            u, v = img(x, y)
            pts.append(CalibrationPoint(image=(u + rng.normal(0, noise), v + rng.normal(0, noise)), pitch=(x, y)))
    return PitchCalibration(points=tuple(pts), image_size=(2000, 1200))


def barrel(x: float, y: float) -> tuple[float, float]:
    """Panoramik kamera benzeri doğrusal olmayan izdüşüm (TPS gerektirir)."""
    u, v = img(x, y)
    du, dv = (u - 1000) / 1000, (v - 400) / 400
    k = 1 + 0.08 * (du * du + dv * dv)
    return 1000 + (u - 1000) * k, 400 + (v - 400) * k


def tps_calib(*, with_corners: bool = True) -> PitchCalibration:
    xs = (0.0, 5.5, 16.5, 52.5, 88.5, 99.5, 105.0)
    ys = (0.0, 13.84, 24.84, 34.0, 43.16, 54.16, 68.0)
    corners = {(0.0, 0.0), (105.0, 0.0), (0.0, 68.0), (105.0, 68.0)}
    pts = [CalibrationPoint(image=barrel(x, y), pitch=(x, y)) for x in xs for y in ys
           if with_corners or (x, y) not in corners]
    return PitchCalibration(points=tuple(pts), image_size=(2000, 1200), method="tps")


BALL = (60.0, 34.0)


def scene() -> list[PlayerSpot]:
    """Takım 0 topla; takım 1 x azalan yöne hücum eder (kalesi x=105)."""
    attackers = [(1, 2, 34), (2, 60, 35), (3, 50, 10), (4, 50, 58), (5, 62, 20), (6, 64, 50), (7, 70, 30)]
    defenders = [
        (20, 103, 34),                                           # kaleci (izole, düşülür)
        (21, 70, 10), (22, 70, 26), (23, 70, 42), (24, 70, 58),  # 35 m: savunma hattı
        (25, 57.5, 34), (26, 60, 38),                            # presçiler (2,5 m ve 4 m)
        (27, 55, 15), (28, 55, 53),                              # orta hat
        (29, 40, 25), (30, 40, 45),                              # forvetler (2 kişi: hat sayılmaz)
    ]
    return ([PlayerSpot(t, 0, x, y) for t, x, y in attackers]
            + [PlayerSpot(t, 1, x, y) for t, x, y in defenders])


def run(t: Telestrator, cal: PitchCalibration | None, frames: int = 10, possession: int | None = None):
    marks = []
    for _ in range(frames):
        marks = t.marks(scene(), BALL, cal, possession)
    return marks


def test_block_label_thresholds() -> None:
    assert block_label(20, False) == "Alçak blok"
    assert block_label(35, True) == "Orta blok · pres"
    assert block_label(50, False) == "Yüksek blok"


def test_ring_is_perspective_ellipse_around_feet() -> None:
    marks = run(Telestrator(fps=5), calib(), frames=1)
    ring = next(m for m in marks if m.kind == "ring")
    pts = np.array(ring.points)
    assert np.allclose(pts.mean(axis=0), img(2, 34), atol=3.0)
    width, height = np.ptp(pts, axis=0)
    assert width > height > 0  # sahaya yatık: yatayda geniş


def test_defending_block_lines_label_and_pressers() -> None:
    marks = run(Telestrator(fps=5), calib())
    assert "Orta blok · pres" in [m.text for m in marks if m.kind == "label"]
    assert "13 m" in [m.text for m in marks if m.kind == "label"]  # 35 m ile 48,1 m arası
    assert sum(m.kind == "line" for m in marks) == 2
    assert any(m.kind == "band" for m in marks)
    assert sum(m.kind == "ring" and m.emphasis for m in marks) == 2
    # savunma hattı x=70'te, uç oyuncularının (y 10–58) 3 m ötesine kadar izdüşmeli
    line = np.array(next(m for m in marks if m.kind == "line").points)
    assert np.allclose(line[0], img(70, 7), atol=1.0)
    assert np.allclose(line[-1], img(70, 61), atol=1.0)


def test_supplied_possession_is_used() -> None:
    # sahiplik deplasmanda denirse (top yakınlığına rağmen) savunan ev sahibi olur
    marks = run(Telestrator(fps=5), calib(), possession=1)
    assert {m.team for m in marks if m.kind in ("line", "band")} == {0}


def test_label_waits_for_hold_period() -> None:
    t = Telestrator(fps=5)  # 1 s = 5 kare
    assert not any(m.kind == "label" and m.points == () for m in run(t, calib(), frames=4))
    assert any(m.kind == "label" and m.points == () for m in run(t, calib(), frames=1))


def test_line_smoothing_damps_jitter_and_resets_on_new_line() -> None:
    t = Telestrator(fps=5)
    assert t._smooth([Line(30.0, 10.0, 50.0)])[0].depth == 30.0
    assert t._smooth([Line(34.0, 10.0, 50.0)])[0].depth == pytest.approx(31.4)   # 0,35·34 + 0,65·30
    assert t._smooth([Line(50.0, 10.0, 50.0)])[0].depth == 50.0                  # 8 m'den büyük sıçrama: yeni hat


def test_untrusted_calibration_draws_rings_only() -> None:
    bad = calib(noise=60.0)
    assert bad.reprojection_error_m > 1.5
    t = Telestrator(fps=5)
    marks = run(t, bad)
    assert {m.kind for m in marks} <= {"ring", "ball"}
    assert t.gate_counts["calibration"] == 10


def test_no_calibration_draws_nothing() -> None:
    t = Telestrator(fps=5)
    assert run(t, None, frames=2) == []
    assert t.gate_counts["calibration"] == 2


def test_unknown_direction_suppresses_label() -> None:
    t = Telestrator(fps=5)
    people = [PlayerSpot(i, i % 2, 52.5, 5 + 6 * i) for i in range(12)]  # iki takımın en derini aynı
    for _ in range(10):
        marks = t.marks(people, (52.5, 5.5), calib())
    assert not any(m.kind in ("label", "line") for m in marks)
    assert t.gate_counts["direction"] == 10


def test_operator_direction_overrides_inference() -> None:
    t = Telestrator(fps=5, home_attack_direction=-1)
    marks = run(t, calib())
    # takım 1 bu kez x artan yöne hücum eder: kalesi x=0, en geri hattı ~57 m → yüksek blok
    assert "Yüksek blok · pres" in [m.text for m in marks if m.kind == "label"]


def test_invalid_direction_rejected() -> None:
    with pytest.raises(ValueError):
        Telestrator(fps=5, home_attack_direction=2)


def test_tps_numeric_inverse_round_trips() -> None:
    cal = tps_calib()
    targets = np.array([[30.0, 20.0], [70.0, 50.0], [52.5, 34.0]])
    proj = _Projector(cal)
    uv, ok = proj.project(targets)
    assert ok.all()
    assert np.allclose(proj.forward(uv), targets, atol=0.1)
    assert np.allclose(proj.forward(uv[:1])[0], cal.image_to_pitch_m(*uv[0]), atol=1e-9)
    assert np.allclose(uv, [barrel(*t) for t in targets], atol=3.0)


def test_tps_scene_draws_lines() -> None:
    marks = run(Telestrator(fps=5), tps_calib())
    assert sum(m.kind == "line" for m in marks) == 2
    assert "Orta blok · pres" in [m.text for m in marks if m.kind == "label"]


def test_tps_without_corners_uses_control_point_hull() -> None:
    proj = _Projector(tps_calib(with_corners=False))  # işaretli sınır yok, zarf köşeleri kırpar
    _uv, ok = proj.project(np.array([[52.5, 34.0], [1.0, 1.0], [104.0, 67.0]]))
    assert ok.tolist() == [True, False, False]  # zarf dışı köşe bölgesi ekstrapolasyondur


def test_collinear_points_have_no_hull() -> None:
    assert _convex_hull(np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])) is None


def test_ball_outside_support_is_ignored() -> None:
    t = Telestrator(fps=5)
    marks = t.marks(scene(), (60.0, -12.0), tps_calib())  # tribün tarafı
    assert not any(m.kind == "ball" for m in marks)


def test_spots_from_frame_maps_teams_and_metres() -> None:
    def pos(pid: int, team: int | None, x: float, y: float) -> PlayerPosition:
        return PlayerPosition(player_external_id=pid, x=x, y=y, team_external_id=team)

    frame = TrackingFrame(sport="football", match_external_id=1, timestamp=datetime(2000, 1, 1, tzinfo=UTC),
                          period=1, minute=0.0, ball=pos(0, None, 50, 50),
                          players=(pos(1, 77, 10, 50), pos(2, 88, 90, 25), pos(3, None, 50, 50)),
                          possession_team_external_id=88)
    players, ball, owner = spots_from_frame(frame, 77, 88, calib())
    assert [(p.team, round(p.x_m, 1), round(p.y_m, 1)) for p in players] == [
        (0, 10.5, 34.0), (1, 94.5, 17.0), (None, 52.5, 34.0)]
    assert ball == (52.5, 34.0)
    assert owner == 1


@pytest.mark.parametrize("width", [960, 1920])
def test_render_draws_turkish_label(width: int) -> None:
    pytest.importorskip("cv2")
    bgr = np.full((width * 9 // 16, width, 3), 40, np.uint8)
    before = bgr.copy()
    render(bgr, run(Telestrator(fps=5), calib()))
    assert (bgr != before).any()


def test_interpolate_spots_by_identity() -> None:
    from app.tracking.telestration import interpolate_point, interpolate_spots

    a = [PlayerSpot(1, 0, 10.0, 10.0), PlayerSpot(2, 1, 50.0, 30.0)]
    b = [PlayerSpot(1, 0, 20.0, 14.0), PlayerSpot(3, 1, 70.0, 40.0)]
    early = interpolate_spots(a, b, 0.25)
    assert [(p.tid, p.x_m, p.y_m) for p in early] == [(1, 12.5, 11.0), (2, 50.0, 30.0)]
    late = interpolate_spots(a, b, 0.75)
    assert [(p.tid, p.x_m) for p in late] == [(1, 17.5), (3, 70.0)]   # yalnız birinde olan yakın karede
    assert interpolate_point((0.0, 0.0), (10.0, 20.0), 0.5) == (5.0, 10.0)
    assert interpolate_point(None, (10.0, 20.0), 0.4) is None


def test_line_smoothing_time_constant_is_fps_independent() -> None:
    slow, fast = Telestrator(fps=5), Telestrator(fps=25)
    slow._smooth([Line(30.0, 0, 1)])
    fast._smooth([Line(30.0, 0, 1)])
    after_slow = slow._smooth([Line(34.0, 0, 1)])[0].depth          # 0,2 sn = 1 kare
    after_fast = 0.0
    for _ in range(5):                                                # 0,2 sn = 5 kare
        after_fast = fast._smooth([Line(34.0, 0, 1)])[0].depth
    assert after_fast == pytest.approx(after_slow)


def test_schedule_interpolates_within_continuity_only() -> None:
    from scripts.telestrate_video import schedule

    spots = [([PlayerSpot(1, 0, float(x), 0.0)], None, 0) for x in (0, 10, 20, 30)]
    seconds = [0.0, 0.2, 0.4, 2.0]           # son aralık 1,6 sn: kopma
    continuity: list[int | None] = [0, 0, 1, 1]  # 0,2 → 0,4 arası kamera kesmesi
    plan = schedule(seconds, spots, continuity, 25.0, interpolate=True)
    xs = {idx: sp[0][0].x_m for idx, _t, sp in plan if sp[0]}
    assert xs[0] == 0.0 and xs[5] == 10.0
    assert xs[2] == pytest.approx(4.0)                    # 0,08 sn: 0 → 10 arasında
    assert 7 not in xs                                    # kesme sonrası boşlukta çizim yok
    assert xs[10] == 20.0 and xs[50] == 30.0              # takip kareleri kendileri
    assert 30 not in xs                                   # uzun boşlukta uydurma yok
    plain = schedule(seconds, spots, continuity, 25.0, interpolate=False)
    assert [idx for idx, *_ in plain] == [0, 5, 10, 50]


@pytest.mark.parametrize("make", [calib, tps_calib])
def test_batched_rings_match_exact_projection(make) -> None:
    proj = _Projector(make())
    centers = np.array([[30.0, 20.0], [70.0, 50.0], [52.5, 34.0]])
    rings, ok = proj.rings(centers, 0.9)
    assert ok.all()
    a = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    for c, ring in zip(centers, rings, strict=True):
        exact = proj(np.c_[c[0] + 0.9 * np.cos(a), c[1] + 0.9 * np.sin(a)])
        assert exact is not None
        assert np.abs(ring - exact).max() < 0.5   # piksel: doğrusal yaklaşım hatası


def test_config_defaults_match_production_and_validate() -> None:
    from app.tracking.telestration import TelestrationConfig

    assert TelestrationConfig() == TelestrationConfig(0.35, 1.0, 0.0, "mean")
    with pytest.raises(ValueError):
        TelestrationConfig(line_statistic="mode")
    with pytest.raises(ValueError):
        TelestrationConfig(line_smoothing=0.0)


def test_short_lived_tracks_stay_out_of_lines_until_steady() -> None:
    from app.tracking.telestration import TelestrationConfig

    t = Telestrator(fps=5, config=TelestrationConfig(min_track_s=1.0))   # 5 kare
    for _ in range(4):
        t.marks(scene(), BALL, calib())
    assert t.last_gate == "players"           # henüz hiçbir oyuncu 1 sn görünmedi
    t.marks(scene(), BALL, calib())
    assert t.last_gate == "drawn"
    ghost = PlayerSpot(999, 1, 66.0, 34.0)    # yeni beliren tek karelik tespit
    t.marks([*scene(), ghost], BALL, calib())
    assert t.last_lines[0].depth == pytest.approx(35.0, abs=0.5)   # hat ona göre kaymadı


def test_median_line_depth_resists_one_outlier() -> None:
    from app.tracking.telestration import _lines

    players = [(30.0, 10.0), (31.0, 20.0), (32.0, 30.0), (37.5, 40.0)]
    assert _lines(players, "mean")[0].depth == pytest.approx(32.625)
    assert _lines(players, "median")[0].depth == pytest.approx(31.5)


def test_player_derived_calibration_is_unverified() -> None:
    from app.tracking.telestration import calibration_validation

    rng = np.random.default_rng(3)
    pitch = rng.uniform([8, 8], [97, 60], size=(30, 2))      # oyuncu konumları: saha işareti değil
    pts = tuple(CalibrationPoint(image=img(x, y), pitch=(float(x), float(y))) for x, y in pitch)
    cal = PitchCalibration(points=pts, image_size=(2000, 1200))
    assert cal.reprojection_error_m < 0.01                    # kendi noktalarında kusursuz görünür
    assert calibration_validation(cal) == ("unverified", None)
    t = Telestrator(fps=5)
    marks = run(t, cal)
    assert t.gate_counts["calibration_unverified"] == 10
    assert not any(m.kind in ("line", "label") for m in marks)


def test_line_validation_in_meta_is_used() -> None:
    from app.tracking.telestration import calibration_validation

    base = calib()
    good = PitchCalibration(points=base.points, image_size=base.image_size,
                            meta={"line_validation_error_m": 1.2})
    bad = PitchCalibration(points=base.points, image_size=base.image_size,
                           meta={"line_validation_error_m": 9.0})
    assert calibration_validation(good) == ("line_validation", 1.2)
    t = Telestrator(fps=5)
    run(t, bad)
    assert t.gate_counts["calibration"] == 10


def test_landmark_calibrations_use_loo() -> None:
    from app.tracking.telestration import calibration_validation

    source, error = calibration_validation(calib())
    assert source == "landmark_loo" and error is not None and error < 0.01
    assert calibration_validation(tps_calib())[0] == "landmark_loo"


def _rendered_dist_map(h_img_to_pitch: np.ndarray, size=(1600, 900)) -> np.ndarray:
    """Saha çizgilerini homografinin tersiyle çiz, en yakın çizgi pikseline uzaklık haritası üret."""
    from scipy.ndimage import distance_transform_edt

    from app.tracking.pitch_model import model_points

    w, h = size
    mask = np.zeros((h, w), dtype=bool)
    pts = model_points(0.1, "all")
    q = np.c_[pts, np.ones(len(pts))] @ np.linalg.inv(h_img_to_pitch).T
    uv = (q[:, :2] / q[:, 2:3]).round().astype(int)
    keep = (q[:, 2] > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    mask[uv[keep, 1], uv[keep, 0]] = True
    return distance_transform_edt(~mask).astype(np.float32)


def test_line_validation_error_detects_misfit_and_missing_lines() -> None:
    from app.tracking.telestration import line_validation_error

    # saha → görüntü: tüm saha 1600×900 karede, hafif perspektif; görüntü → saha bunun tersi
    pitch_to_img = np.array([[13.0, 3.0, 80.0], [0.0, 10.0, 120.0], [0.0, 0.002, 1.0]])
    h_true = np.linalg.inv(pitch_to_img)
    dist = _rendered_dist_map(h_true)
    err, coverage = line_validation_error(h_true, dist)
    assert err is not None and err < 0.15 and coverage > 0.95
    shift = np.array([[1.0, 0.0, 3.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])   # 3 m kaymış oturma
    err_shift, _ = line_validation_error(shift @ h_true, dist)
    assert err_shift is None or err_shift > 0.5
    y_shift = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 3.0], [0.0, 0.0, 1.0]])   # enine 3 m
    err_y, _ = line_validation_error(y_shift @ h_true, dist)
    assert err_y is None or err_y > 0.5
    none_err, none_cov = line_validation_error(h_true, np.full_like(dist, 500.0))
    assert none_err is None and none_cov == 0.0
