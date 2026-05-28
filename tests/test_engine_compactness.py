"""engine.compactness — savunma-orta-hücum bandı dağınıklığı tests."""

from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.compactness import compute_compactness


def _p(team: int, sx: float) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        start_x=sx, start_y=50, end_x=sx + 5, end_y=50,
    )


def _d(team: int, x: float) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=10.0, period=1,
        x=x, y=50, action_type="tackle",
    )


def test_compact_block():
    """Defansif aksiyonlar dar x-bandında (30-40) → compact."""
    passes = [_p(11, x) for x in [30, 32, 35, 38, 40]]
    defs = [_d(11, x) for x in [25, 28, 30, 32, 35]]
    r = compute_compactness(11, passes, defs).value
    assert r.label == "compact"
    assert r.overall_stdev < 18


def test_stretched_team():
    """Geniş x dağılımı → stretched."""
    passes = [_p(11, x) for x in [10, 30, 50, 70, 90]]
    defs = [_d(11, x) for x in [5, 25, 50, 70, 95]]
    r = compute_compactness(11, passes, defs).value
    assert r.label == "stretched"


def test_balanced_intermediate():
    """Stdev 18-28 arası → balanced."""
    passes = [_p(11, x) for x in [20, 35, 50, 65, 80]]   # stdev ~23.7
    defs = [_d(11, x) for x in [25, 40, 50, 60, 75]]
    r = compute_compactness(11, passes, defs).value
    assert r.label == "balanced", f"stdev={r.overall_stdev}"


def test_opponent_excluded():
    passes = [_p(22, x) for x in [10, 90]]  # rakip
    defs = [_d(11, 30)]
    r = compute_compactness(11, passes, defs).value
    assert r.passes_counted == 0
    assert r.def_actions_counted == 1


def test_empty_insufficient_data():
    r = compute_compactness(11, [], []).value
    assert r.label == "insufficient_data"


def test_audit_present():
    r = compute_compactness(11, [], [])
    assert r.audit.engine == "engine.compactness"
    assert "compact_stdev_max" in r.audit.inputs
