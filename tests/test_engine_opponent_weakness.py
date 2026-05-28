"""engine.opponent_weakness — zayıf kanal tespiti tests."""

from __future__ import annotations

from app.domain import Carry, DefensiveAction, PassEvent
from app.engine.opponent_weakness import compute_opponent_weakness


def _p(team: int, sx: float, ex: float, ey: float) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
    )


def _c(team: int, sx: float, ex: float, ey: float) -> Carry:
    return Carry(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=ex, end_y=ey,
    )


def _d(team: int, y: float) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        x=20, y=y, action_type="tackle",
    )


def test_left_channel_most_vulnerable():
    """Bizim sol kanaldan 10 atak, rakibin orada 1 savunma → sol zayıf."""
    passes = [_p(11, sx=50, ex=80, ey=15)] * 10  # sol giriş
    defs = [_d(22, y=15)]  # rakibin sol-x'te 1 savunma
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=passes, all_carries=[], all_def_actions=defs,
    ).value
    assert r.most_vulnerable_channel == "left"


def test_balanced_attacks_central_default():
    """3 kanaldan eşit atak, rakip eşit savunma → en yüksek score eşitlik."""
    passes = (
        [_p(11, sx=50, ex=80, ey=15)] * 3 +
        [_p(11, sx=50, ex=80, ey=50)] * 3 +
        [_p(11, sx=50, ex=80, ey=85)] * 3
    )
    defs = [_d(22, y=15), _d(22, y=50), _d(22, y=85)]
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=passes, all_carries=[], all_def_actions=defs,
    ).value
    # Üçü de aynı vulnerability_score (eşit)
    scores = [c.vulnerability_score for c in r.by_channel]
    assert len(set(scores)) == 1


def test_includes_carries():
    """Carry'ler de saldırı sayar."""
    carries = [_c(11, sx=50, ex=80, ey=85)] * 5  # sağ
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=[], all_carries=carries, all_def_actions=[],
    ).value
    right = next(c for c in r.by_channel if c.channel == "right")
    assert right.our_attacks == 5


def test_recommendation_human_readable():
    passes = [_p(11, sx=50, ex=80, ey=85)] * 8  # sağ
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=passes, all_carries=[], all_def_actions=[],
    ).value
    assert "sağ" in r.recommendation


def test_no_attacks_handled():
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=[], all_carries=[], all_def_actions=[],
    ).value
    assert r.most_vulnerable_channel in ("left", "central", "right")
    assert "Yeterli veri yok" in r.recommendation


def test_own_team_defs_ignored():
    """Bizim defansif aksiyon rakip filtresi düşürür."""
    passes = [_p(11, sx=50, ex=80, ey=15)] * 5
    defs = [_d(11, y=15)] * 10  # bizim, rakip değil
    r = compute_opponent_weakness(
        my_team_external_id=11, opponent_team_external_id=22,
        all_passes=passes, all_carries=[], all_def_actions=defs,
    ).value
    left = next(c for c in r.by_channel if c.channel == "left")
    assert left.opp_def_actions == 0
