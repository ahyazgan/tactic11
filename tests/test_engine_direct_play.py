"""engine.direct_play tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.direct_play import compute_direct_play


def _p(team: int, sx: float, sy: float, ex: float, ey: float) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
    )


def test_direct_style_vertical_passes():
    """Tüm paslar tamamen ileri (dikey) → directness ~1.0."""
    passes = [_p(11, 20, 50, 50, 50) for _ in range(5)]
    r = compute_direct_play(11, passes).value
    assert r.avg_directness >= 0.95
    assert r.style_label == "direct"


def test_possession_style_lateral():
    """Tüm paslar yatay → directness 0."""
    passes = [_p(11, 50, 30, 50, 60) for _ in range(5)]
    r = compute_direct_play(11, passes).value
    assert r.avg_directness == 0.0
    assert r.style_label == "possession"


def test_balanced_mix():
    """Yarım ileri, yarım yatay → balanced."""
    passes = (
        [_p(11, 20, 50, 50, 50)] * 5 +     # vertical 1.0
        [_p(11, 50, 30, 50, 60)] * 5        # lateral 0.0
    )
    r = compute_direct_play(11, passes).value
    assert r.style_label == "balanced"


def test_short_passes_filtered():
    """1 birim altı paslar gürültü, atlanır."""
    passes = [_p(11, 50, 50, 50.5, 50.2)]  # ~0.5 birim
    r = compute_direct_play(11, passes).value
    assert r.passes_analyzed == 0


def test_opponent_excluded():
    passes = [_p(22, 20, 50, 50, 50)]
    r = compute_direct_play(11, passes).value
    assert r.passes_analyzed == 0


def test_forward_pass_share():
    passes = [_p(11, 20, 50, 50, 50), _p(11, 50, 50, 30, 50)]  # 1 ileri, 1 geri
    r = compute_direct_play(11, passes).value
    assert r.forward_pass_share == 0.5
