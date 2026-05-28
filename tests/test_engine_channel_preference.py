"""engine.channel_preference — koridor dağılımı tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.channel_preference import compute_channel_preference


def _p(team: int, sx: float, sy: float) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=sy, end_x=sx + 5, end_y=sy,
    )


def test_left_dominant():
    passes = [_p(11, 75, 15) for _ in range(5)]  # tüm paslar sol kanat
    r = compute_channel_preference(11, passes).value
    assert r.dominant_channel == "left"
    assert r.left_share == 1.0


def test_right_dominant():
    passes = [_p(11, 75, 85) for _ in range(5)]
    r = compute_channel_preference(11, passes).value
    assert r.dominant_channel == "right"


def test_central_dominant():
    passes = [_p(11, 75, 50) for _ in range(5)]
    r = compute_channel_preference(11, passes).value
    assert r.dominant_channel == "central"


def test_balanced():
    """3 kanal eşit dağılım → balanced."""
    passes = (
        [_p(11, 75, 15) for _ in range(4)] +  # 4 sol
        [_p(11, 75, 50) for _ in range(4)] +  # 4 orta
        [_p(11, 75, 85) for _ in range(4)]    # 4 sağ
    )
    r = compute_channel_preference(11, passes).value
    assert r.dominant_channel == "balanced"


def test_attacking_third_filter():
    """Saha ortası pasları sayılmaz (x < 66.7)."""
    passes = [_p(11, 50, 15)]  # orta sahadan, sol y
    r = compute_channel_preference(11, passes).value
    assert r.total_attacking_passes == 0


def test_opponent_excluded():
    passes = [_p(22, 75, 15)]  # rakip
    r = compute_channel_preference(11, passes).value
    assert r.total_attacking_passes == 0
