from __future__ import annotations

from app.domain import TrackingFrame
from scripts.soccertrack_v2.eval_shape_watch import alt_widths


def frame(players: list[tuple[int, float, float]], keeper_ids: set[int] = frozenset()) -> TrackingFrame:
    return TrackingFrame.model_validate({
        "sport": "football", "match_external_id": 1, "timestamp": "2000-01-01T00:10:00Z", "period": 1, "minute": 10.0,
        "ball": None, "ball_estimated": False, "source": "video_tracking", "event_type": "video_sample",
        "possession_team_external_id": None, "visible_area": None,
        "players": [{"player_external_id": pid, "x": x / 105 * 100, "y": y / 68 * 100, "velocity_mps": None,
                     "team_external_id": 7, "is_actor": False, "is_keeper": pid in keeper_ids, "identity_estimated": True}
                    for pid, x, y in players]})


def test_robust_width_and_length_ignore_a_single_outlier() -> None:
    base = [(i, 30.0 + 2 * i, 20.0 + 3 * i) for i in range(9)]            # y 20..44, depth 30..46
    clean = alt_widths(frame(base), 7, 1)
    with_ghost = alt_widths(frame(base + [(99, 90.0, 66.0)]), 7, 1)        # hayalet: en ileri ve en kenar
    assert clean is not None and with_ghost is not None
    assert abs(with_ghost["width_p10_90"] - clean["width_p10_90"]) < 4.0   # en–en 22 m büyürdü
    assert abs(with_ghost["length_p90"] - clean["length_p90"]) < 6.0        # en ileri oyuncu tanımı 44 m büyürdü
    assert alt_widths(frame(base[:5]), 7, 1) is None and alt_widths(frame(base), 7, 0) is None
    assert alt_widths(frame(base, keeper_ids={0}), 7, 1)["width_trim1"] < clean["width_trim1"]
