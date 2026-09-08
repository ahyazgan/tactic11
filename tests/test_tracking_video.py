"""Video takibi çekirdeği — kalibrasyon, takım kümeleme, kare inşası, JSON kaynak (torch'suz)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.data.ingest.tracking import ingest_tracking_match
from app.data.sources.video_tracking import VideoJsonTrackingSource
from app.db import models
from app.tracking.calibration import CalibrationError, PitchCalibration, dlt_homography
from app.tracking.frames import (
    VIDEO_PLAYER_BASE_ID,
    BallObservation,
    TrackObservation,
    build_frame,
    frames_from_json,
    frames_to_json,
)
from app.tracking.teams import TeamAssigner, kmeans2, torso_color

# --------------------------------------------------------------------------- #
# Kalibrasyon
# --------------------------------------------------------------------------- #


def _topdown_calib(scale: float = 10.0, offset: tuple[float, float] = (100.0, 50.0)) -> PitchCalibration:
    """Tepeden bakış: piksel = saha_m * scale + offset (saf afin)."""
    corners_m = [(0, 0), (105, 0), (105, 68), (0, 68), (52.5, 34)]
    return PitchCalibration.from_dict({
        "image_size": [1300, 800],
        "points": [
            {"image": [x * scale + offset[0], y * scale + offset[1]], "pitch": [x, y]}
            for x, y in corners_m
        ],
    })


def test_dlt_recovers_affine_mapping() -> None:
    src = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]], dtype=float)
    dst = src * 3.0 + np.array([7.0, -2.0])
    H = dlt_homography(src, dst)
    p = H @ np.array([2.0, 4.0, 1.0])
    assert p[0] / p[2] == pytest.approx(13.0, abs=1e-6)
    assert p[1] / p[2] == pytest.approx(10.0, abs=1e-6)


def test_dlt_projective_case() -> None:
    """Perspektif (paralel olmayan) dörtgen → dikdörtgen."""
    src = np.array([[100, 400], [900, 400], [1000, 700], [0, 700]], dtype=float)
    dst = np.array([[0, 0], [105, 0], [105, 68], [0, 68]], dtype=float)
    H = dlt_homography(src, dst)
    for (u, v), (x, y) in zip(src, dst, strict=True):
        p = H @ np.array([u, v, 1.0])
        assert p[0] / p[2] == pytest.approx(x, abs=1e-6)
        assert p[1] / p[2] == pytest.approx(y, abs=1e-6)


def test_calibration_requires_four_points() -> None:
    with pytest.raises(CalibrationError):
        PitchCalibration.from_dict({"image_size": [10, 10], "points": [
            {"image": [0, 0], "pitch": [0, 0]}, {"image": [1, 0], "pitch": [1, 0]},
        ]})


def test_calibration_degenerate_points_raise() -> None:
    calib = PitchCalibration.from_dict({"image_size": [10, 10], "points": [
        {"image": [i, i], "pitch": [i, 0]} for i in range(5)
    ]})
    with pytest.raises(CalibrationError):
        _ = calib.homography


def test_image_to_normalized_and_clamp() -> None:
    c = _topdown_calib()
    assert c.image_to_normalized(100 + 52.5 * 10, 50 + 34 * 10) == (50.0, 50.0)
    assert c.image_to_normalized(100 + 105 * 10, 50 + 68 * 10) == (100.0, 100.0)
    # Saha dışı → clamp
    assert c.image_to_normalized(0, 0) == (0.0, 0.0)
    assert c.image_to_normalized(0, 0, clamp=False)[0] < 0
    assert c.reprojection_error_m < 1e-6


def test_is_on_pitch_margin() -> None:
    c = _topdown_calib()
    assert c.is_on_pitch(100 + 10 * 10, 50 + 10 * 10)
    assert not c.is_on_pitch(100 - 5 * 10, 50 + 10 * 10)      # 5 m dışarıda
    assert c.is_on_pitch(100 - 1 * 10, 50 + 10 * 10)          # 1 m → marj içinde


def test_visible_area_projects_image_corners() -> None:
    c = _topdown_calib()
    area = c.visible_area_normalized()
    assert len(area) == 4
    assert area[0] == (0.0, 0.0)           # görüntü (0,0) saha dışına düşer → clamp
    assert area[2] == (100.0, 100.0)


def test_calibration_json_roundtrip(tmp_path) -> None:
    c = _topdown_calib()
    p = tmp_path / "calib.json"
    c.save(p)
    c2 = PitchCalibration.load(p)
    assert c2.image_size == (1300, 800)
    assert c2.image_to_normalized(600, 400) == c.image_to_normalized(600, 400)


# --------------------------------------------------------------------------- #
# Takım kümeleme
# --------------------------------------------------------------------------- #


def test_kmeans2_separates_two_colors() -> None:
    reds = np.array([[220, 30, 30], [200, 40, 50], [230, 20, 35]], dtype=float)
    blues = np.array([[30, 40, 220], [40, 50, 200], [20, 30, 230]], dtype=float)
    labels, centers = kmeans2(np.vstack([reds, blues]))
    assert len(set(labels[:3])) == 1 and len(set(labels[3:])) == 1
    assert labels[0] != labels[3]
    assert centers.shape == (2, 3)


def test_team_assigner_marks_outlier_as_none() -> None:
    a = TeamAssigner(min_observations=1)
    for t in (1, 2, 3):
        a.observe(t, np.array([220, 30, 30]))
        a.observe(t, np.array([210, 35, 40]))
    for t in (4, 5, 6):
        a.observe(t, np.array([30, 40, 220]))
        a.observe(t, np.array([35, 45, 210]))
    a.observe(9, np.array([250, 240, 30]))   # sarı hakem
    res = a.fit()
    assert {res.team_by_track[t] for t in (1, 2, 3)} == {res.team_by_track[1]}
    assert res.team_by_track[1] != res.team_by_track[4]
    assert res.team_by_track[9] is None
    assert 9 in res.outlier_tracks


def test_torso_color_ignores_grass() -> None:
    img = np.zeros((100, 60, 3), dtype=np.uint8)
    img[:, :] = (40, 200, 50)             # çim
    img[15:55, 12:48] = (230, 30, 30)     # gövde bölgesi kırmızı forma
    col = torso_color(img, (0, 0, 60, 100))
    assert col is not None
    assert col[0] > 200 and col[1] < 60


# --------------------------------------------------------------------------- #
# Kare inşası
# --------------------------------------------------------------------------- #


def test_build_frame_maps_players_ball_actor_and_teams() -> None:
    c = _topdown_calib()
    players = [
        TrackObservation(track_id=7, u=100 + 20 * 10, v=50 + 34 * 10, team=0),
        TrackObservation(track_id=8, u=100 + 21 * 10, v=50 + 34 * 10, team=1),
        TrackObservation(track_id=9, u=100 + 90 * 10, v=50 + 10 * 10, team=None),
        TrackObservation(track_id=10, u=100 - 8 * 10, v=50 + 10 * 10, team=0),   # 8 m saha dışı → atılır
    ]
    ball = BallObservation(u=100 + 20.3 * 10, v=50 + 34 * 10)
    fr = build_frame(
        match_id=990001, seconds=12.0, order=60, calib=c, players=players, ball=ball,
        home_team_id=217, away_team_id=213, clip_offset_minutes=30.0,
    )
    assert fr is not None
    assert fr.source == "video_tracking"
    assert fr.minute == pytest.approx(30.2)
    assert fr.ball is not None and fr.ball.x == pytest.approx(19.333, abs=0.01)
    ids = {p.player_external_id for p in fr.players}
    assert ids == {VIDEO_PLAYER_BASE_ID + 7, VIDEO_PLAYER_BASE_ID + 8, VIDEO_PLAYER_BASE_ID + 9}
    by_id = {p.player_external_id: p for p in fr.players}
    assert by_id[VIDEO_PLAYER_BASE_ID + 7].team_external_id == 217
    assert by_id[VIDEO_PLAYER_BASE_ID + 8].team_external_id == 213
    assert by_id[VIDEO_PLAYER_BASE_ID + 9].team_external_id is None
    # Top 20.3 m'de → 7 (20 m) en yakın (0.3 m < 2.5 m)
    actors = [p for p in fr.players if p.is_actor]
    assert len(actors) == 1 and actors[0].player_external_id == VIDEO_PLAYER_BASE_ID + 7
    assert fr.possession_team_external_id == 217
    assert all(p.identity_estimated for p in fr.players)
    assert fr.visible_area is not None and len(fr.visible_area) == 4


def test_build_frame_returns_none_when_nobody_on_pitch() -> None:
    c = _topdown_calib()
    fr = build_frame(
        match_id=1, seconds=0, order=0, calib=c,
        players=[TrackObservation(1, u=0, v=0, team=0)], ball=None,
        home_team_id=1, away_team_id=2,
    )
    assert fr is None


def test_build_frame_no_actor_without_ball() -> None:
    c = _topdown_calib()
    fr = build_frame(
        match_id=1, seconds=1, order=1, calib=c,
        players=[TrackObservation(1, u=600, v=400, team=1)], ball=None,
        home_team_id=1, away_team_id=2,
    )
    assert fr is not None and not any(p.is_actor for p in fr.players)
    assert fr.possession_team_external_id is None


def test_timestamps_unique_within_same_second() -> None:
    c = _topdown_calib()
    a = build_frame(match_id=1, seconds=1.0, order=5, calib=c,
                    players=[TrackObservation(1, 600, 400, 0)], ball=None, home_team_id=1, away_team_id=2)
    b = build_frame(match_id=1, seconds=1.0, order=6, calib=c,
                    players=[TrackObservation(1, 600, 400, 0)], ball=None, home_team_id=1, away_team_id=2)
    assert a is not None and b is not None and a.timestamp != b.timestamp


# --------------------------------------------------------------------------- #
# Hat yardımcıları (torch'suz): top enterpolasyonu, hız
# --------------------------------------------------------------------------- #


def _sample(order: int, persons=(), ball=None, src=None):
    from app.tracking.pipeline import SampledObservation

    return SampledObservation(order=order, frame_idx=order * 2, seconds=order / 15.0,
                              persons=list(persons), ball=ball, ball_source=src)


def test_interpolate_ball_fills_short_gaps_only() -> None:
    from app.tracking.pipeline import interpolate_ball

    s = [_sample(0, ball=(100.0, 100.0, 0.9), src="det"), _sample(1), _sample(2),
         _sample(3, ball=(400.0, 100.0, 0.9), src="det"),
         _sample(4), _sample(5), _sample(6), _sample(7), _sample(8),
         _sample(9, ball=(400.0, 700.0, 0.9), src="det")]
    filled = interpolate_ball(s, max_gap=3)
    assert filled == 2
    assert s[1].ball == (200.0, 100.0, 0.0) and s[1].ball_source == "interp"
    assert s[2].ball == (300.0, 100.0, 0.0)
    # 5 örneklik boşluk > max_gap → dolmaz
    assert all(s[i].ball is None for i in range(4, 9))


def test_compute_velocities_central_difference_and_caps() -> None:
    from app.tracking.pipeline import MAX_BALL_SPEED_MPS, compute_velocities

    c = _topdown_calib()  # 10 px = 1 m
    # Oyuncu 7: her örnekte +10 px (1 m) → 15 fps'te 15 m/s → 12 m/s'ye kırpılır
    # Oyuncu 8: her örnekte +2 px (0.2 m) → 3 m/s
    def person(tid, u):
        return (tid, u - 15, 400 - 40, u + 15, 400, 0.9)

    s = [_sample(i, persons=[person(7, 600 + 10 * i), person(8, 800 + 2 * i)],
                 ball=(700 + 100 * i, 400, 0.9), src="det") for i in range(4)]
    pv, bv = compute_velocities(s, c, track_fps=15.0)
    assert pv[1][7] == 12.0                  # kırpıldı
    assert pv[1][8] == pytest.approx(3.0, abs=0.05)
    assert pv[0][8] == pytest.approx(3.0, abs=0.05)   # kenar: tek yönlü fark
    assert bv[1] == MAX_BALL_SPEED_MPS       # 10 m/örnek × 15 = 150 m/s → 45'e kırpıldı


def test_build_frame_carries_velocity_and_ball_estimated() -> None:
    c = _topdown_calib()
    fr = build_frame(
        match_id=1, seconds=0, order=0, calib=c,
        players=[TrackObservation(1, 600, 400, 0, velocity_mps=4.2)],
        ball=BallObservation(605, 400, velocity_mps=20.0),
        home_team_id=1, away_team_id=2, ball_estimated=True,
    )
    assert fr is not None
    assert fr.players[0].velocity_mps == 4.2
    assert fr.ball is not None and fr.ball.velocity_mps == 20.0
    assert fr.ball_estimated is True


# --------------------------------------------------------------------------- #
# JSON → kaynak → ingest
# --------------------------------------------------------------------------- #


def test_json_roundtrip_and_ingest(session, tmp_path) -> None:
    c = _topdown_calib()
    frames = [
        build_frame(match_id=990001, seconds=s, order=i, calib=c,
                    players=[TrackObservation(1, 600, 400, 0), TrackObservation(2, 700, 400, 1)],
                    ball=BallObservation(605, 400), home_team_id=217, away_team_id=213)
        for i, s in enumerate([0.0, 0.2, 0.4])
    ]
    payload = frames_to_json([f for f in frames if f], match_id=990001, extra={"video": "x.mp4"})
    path = tmp_path / "frames.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    back = frames_from_json(json.loads(path.read_text(encoding="utf-8")), match_id=990002)
    assert len(back) == 3 and back[0].match_external_id == 990002
    assert back[0].players[0].team_external_id == 217

    report = ingest_tracking_match(session, VideoJsonTrackingSource(path), match_external_id=990002)
    session.commit()
    assert report.frames_written == 3
    row = session.query(models.TrackingFrameRow).filter_by(match_external_id=990002).first()
    assert row is not None
    meta = json.loads(row.meta_json)
    assert meta["source"] == "video_tracking"
    assert len(meta["visible_area"]) == 4
    players = json.loads(row.players_json)
    assert players[0]["identity_estimated"] is True
