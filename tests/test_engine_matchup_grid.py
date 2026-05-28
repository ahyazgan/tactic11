"""engine.matchup_grid — rakip zaaf × bizim güç tests."""
from __future__ import annotations

from app.domain import Carry, DefensiveAction, PassEvent
from app.engine.matchup_grid import compute_matchup_grid


def _p(team: int, sx: float, ex: float, ey: float) -> PassEvent:
    return PassEvent(
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


def test_best_channel_where_we_attack_opp_weak():
    """Biz sol kanattan çok atak + rakip solda az savunma → best=left."""
    # 10 sol atak (final third girişi)
    passes = [_p(11, sx=50, ex=80, ey=15) for _ in range(10)]
    # Rakip sağda yoğun savunma (sol boş)
    defs = [_d(22, y=85) for _ in range(10)]
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=passes, our_carries=[], opponent_def_actions=defs,
    ).value
    assert r.best_channel == "left"


def test_verdict_exploit_for_best():
    passes = [_p(11, sx=50, ex=80, ey=15) for _ in range(10)]
    defs = [_d(22, y=85) for _ in range(10)]
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=passes, our_carries=[], opponent_def_actions=defs,
    ).value
    left = next(c for c in r.by_channel if c.channel == "left")
    assert left.verdict == "exploit"


def test_carries_count_as_attacks():
    carries = [
        Carry(sport="football", match_external_id=99, player_external_id=1,
              team_external_id=11, minute=10.0, period=1,
              start_x=50, start_y=50, end_x=80, end_y=85)
        for _ in range(5)
    ]
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=[], our_carries=carries, opponent_def_actions=[],
    ).value
    right = next(c for c in r.by_channel if c.channel == "right")
    assert right.our_attacks == 5


def test_no_data_handled():
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=[], our_carries=[], opponent_def_actions=[],
    ).value
    assert "Yeterli atak" in r.recommendation


def test_opponent_filter():
    """Bizim defansif aksiyon rakip filtresinden düşer."""
    passes = [_p(11, sx=50, ex=80, ey=15) for _ in range(5)]
    defs = [_d(11, y=15) for _ in range(10)]  # bizim, rakip değil
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=passes, our_carries=[], opponent_def_actions=defs,
    ).value
    left = next(c for c in r.by_channel if c.channel == "left")
    assert left.opp_def_actions == 0


def test_audit_includes_channels():
    passes = [_p(11, sx=50, ex=80, ey=50) for _ in range(5)]
    r = compute_matchup_grid(
        my_team_external_id=11, opponent_team_external_id=22,
        our_passes=passes, our_carries=[], opponent_def_actions=[],
    )
    assert "by_channel" in r.audit.value
    assert len(r.audit.value["by_channel"]) == 3
