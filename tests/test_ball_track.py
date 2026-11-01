from __future__ import annotations

from app.tracking.ball_track import BallTrackConfig, clean_ball, static_runs


def frame(t: float, ball: tuple[float, float] | None, players: list[tuple[int, float, float]]) -> dict:
    """t sn; konumlar metre (105 × 68) → frames JSON yüzdesi."""
    def pos(x: float, y: float) -> dict:
        return {"x": x / 105 * 100, "y": y / 68 * 100}
    return {"minute": t / 60, "ball": ({"player_external_id": 0, **pos(*ball)} if ball else None),
            "ball_estimated": False,
            "players": [{"player_external_id": pid, "team_external_id": 1, **pos(x, y)} for pid, x, y in players]}


def test_static_object_without_players_is_removed() -> None:
    frames = [frame(i * 0.2, (60.0, 66.0), [(1, 30.0, 30.0)]) for i in range(20)]  # 3,8 sn yerinde
    assert static_runs(frames, BallTrackConfig()) == [(0, 19)]
    stats = clean_ball(frames, BallTrackConfig())
    assert stats["static_removed"] == 20
    assert all(f["ball"] is None for f in frames)


def test_dead_ball_next_to_player_is_kept() -> None:
    frames = [frame(i * 0.2, (60.0, 30.0), [(1, 61.0, 30.0)]) for i in range(20)]
    assert static_runs(frames, BallTrackConfig()) == []


def test_short_stop_is_not_static() -> None:
    frames = [frame(i * 0.2, (60.0, 66.0), [(1, 30.0, 30.0)]) for i in range(10)]  # 1,8 sn
    assert static_runs(frames, BallTrackConfig()) == []


def test_candidate_track_prefers_consistent_motion_over_isolated_noise() -> None:
    from app.tracking.ball_track import CandidateTrackConfig, track_candidates

    times = [i * 0.08 for i in range(12)]
    # gerçek top: 0,15 güvenle sürekli sağa (10 m/sn); gürültü: tek karede 0,35 uzakta
    points = [[(30.0 + 0.8 * i, 20.0, 0.15)] for i in range(12)]
    points[5].append((80.0, 60.0, 0.35))
    track = track_candidates(times, points, CandidateTrackConfig())
    assert all(p is not None for p in track)
    assert all(abs(p.y - 20.0) < 1e-6 for p in track if p is not None)


def test_candidate_track_drops_lone_low_confidence() -> None:
    from app.tracking.ball_track import track_candidates

    times = [i * 0.08 for i in range(5)]
    assert track_candidates(times, [[], [(50.0, 30.0, 0.12)], [], [], []]) == [None] * 5


def test_candidate_track_interpolates_short_gap_only() -> None:
    from app.tracking.ball_track import track_candidates

    times = [i * 0.08 for i in range(30)]
    points: list[list[tuple[float, float, float]]] = [[] for _ in times]
    points[0] = [(10.0, 10.0, 0.6)]
    points[5] = [(12.0, 10.0, 0.6)]       # 0,4 sn sonra → arası doldurulur
    points[25] = [(13.0, 10.0, 0.9)]      # 1,6 sn sonra → bağlanmaz (max_gap 1,5); tek başına yeter
    track = track_candidates(times, points)
    assert [p.source for p in track[:6] if p] == ["cand", "interp", "interp", "interp", "interp", "cand"]
    assert all(p is None for p in track[6:25])
    assert track[25] is not None and track[25].source == "cand"


def test_recompute_actors_follows_the_refined_ball() -> None:
    from app.tracking.ball_track import recompute_actors

    frames = [frame(0.0, (50.0, 30.0), [(7, 50.5, 30.0), (8, 60.0, 30.0)])]
    frames[0]["players"][1]["is_actor"] = True                      # eski topa göre kalmış aktör
    frames[0]["possession_team_external_id"] = 99
    assert recompute_actors(frames) == 1
    assert [p["is_actor"] for p in frames[0]["players"]] == [True, False]
    assert frames[0]["possession_team_external_id"] == 1
    far = [frame(0.0, (50.0, 30.0), [(7, 55.0, 30.0)])]             # 5 m: aktör yok
    recompute_actors(far)
    assert far[0]["possession_team_external_id"] is None and not far[0]["players"][0]["is_actor"]
