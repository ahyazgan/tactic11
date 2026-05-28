"""engine.possession_quality tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.possession_quality import compute_possession_quality


def _p(team: int, poss: int, sx: float = 50, ex: float = 55,
       minute: float = 10.0) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=50,
        possession_id=poss,
    )


def _s(minute: float, is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=90, y=50, is_goal=is_goal,
    )


def test_elite_long_progressing_sequences():
    """Uzun pas zincirleri + ileri ilerleme + şutla biten → elite."""
    passes = (
        [_p(11, 1, sx=20, ex=35, minute=10.0),
         _p(11, 1, sx=35, ex=55, minute=10.05),
         _p(11, 1, sx=55, ex=75, minute=10.10),
         _p(11, 1, sx=75, ex=90, minute=10.15)] +
        [_p(11, 2, sx=20, ex=35, minute=20.0),
         _p(11, 2, sx=35, ex=55, minute=20.05),
         _p(11, 2, sx=55, ex=80, minute=20.10)]
    )
    shots = [_s(10.20, is_goal=True), _s(20.15)]
    r = compute_possession_quality(11, passes, shots).value
    assert r.sequences_analyzed == 2
    assert r.shot_ending_share == 1.0
    assert r.label in ("good", "elite")


def test_weak_short_no_progression():
    """Çok kısa zincirler, ileri ilerleme yok → weak."""
    passes = [_p(11, 1, sx=50, ex=50)]   # tek pas, 0 ilerleme
    r = compute_possession_quality(11, passes, []).value
    assert r.label == "weak"


def test_insufficient_data():
    r = compute_possession_quality(11, [], []).value
    assert r.label == "insufficient_data"


def test_opponent_possessions_excluded():
    passes = [_p(22, 1, sx=20, ex=80)]
    r = compute_possession_quality(11, passes, []).value
    assert r.sequences_analyzed == 0


def test_shot_ending_window():
    """Şut son pas'tan 30 sn sonrasıysa → eşleşmez (0.20 dk üst sınır)."""
    passes = [_p(11, 1, sx=50, ex=70, minute=10.0)]
    shots = [_s(10.50)]
    r = compute_possession_quality(11, passes, shots).value
    assert r.shot_ending_share == 0.0
