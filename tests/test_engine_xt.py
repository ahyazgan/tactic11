"""engine.xt — Expected Threat tests."""

from __future__ import annotations

from app.domain import Carry, PassEvent
from app.engine.xt import (
    GRID_X,
    GRID_Y,
    XT_MATRIX,
    compute_player_xt,
    compute_team_xt,
    xt_value_at,
)


def _pass(
    pid: int, sx: float, sy: float, ex: float, ey: float,
    *, completed: bool = True, team_id: int = 1,
) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=pid, team_external_id=team_id,
        minute=10.0, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
        completed=completed,
    )


def _carry(
    pid: int, sx: float, sy: float, ex: float, ey: float,
    *, team_id: int = 1,
) -> Carry:
    return Carry(
        sport="football", match_external_id=1,
        player_external_id=pid, team_external_id=team_id,
        minute=10.0, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
    )


# --------------------------------------------------------------------------- #
# Grid + xt_value_at
# --------------------------------------------------------------------------- #


def test_grid_shape():
    assert GRID_X == 12 and GRID_Y == 8
    assert len(XT_MATRIX) == GRID_X
    for row in XT_MATRIX:
        assert len(row) == GRID_Y


def test_xt_value_increases_toward_goal():
    """Defansif zone'dan kale önüne doğru xT artmalı."""
    defansif = xt_value_at(5.0, 50.0)
    orta = xt_value_at(50.0, 50.0)
    kale_onu = xt_value_at(95.0, 50.0)
    assert defansif < orta < kale_onu


def test_xt_value_higher_centrally():
    """Aynı x'te kale ortasına yakın daha yüksek xT."""
    sag_kanat = xt_value_at(90.0, 5.0)
    orta = xt_value_at(90.0, 50.0)
    sol_kanat = xt_value_at(90.0, 95.0)
    assert orta > sag_kanat
    assert orta > sol_kanat


def test_xt_value_at_corners():
    """Sınır koordinatlar OK çalışıyor."""
    assert xt_value_at(0.0, 0.0) >= 0
    assert xt_value_at(100.0, 100.0) >= 0


# --------------------------------------------------------------------------- #
# Player xT
# --------------------------------------------------------------------------- #


def test_completed_pass_to_dangerous_zone_adds_xt():
    """Orta sahadan kale önüne tamamlanmış pas → pozitif xT."""
    passes = [_pass(1, sx=50, sy=50, ex=92, ey=50, completed=True)]
    r = compute_player_xt(1, passes, [], minutes_played=90)
    assert r.value.xt_added > 0
    assert r.value.xt_lost == 0
    assert r.value.actions == 1


def test_incomplete_pass_loses_xt():
    """Tamamlanmamış pas başlangıç zone değerini kaybeder."""
    passes = [_pass(1, sx=80, sy=50, ex=99, ey=50, completed=False)]
    r = compute_player_xt(1, passes, [], minutes_played=90)
    assert r.value.xt_lost > 0
    assert r.value.xt_added == 0


def test_xt_net_difference():
    """1 başarılı + 1 başarısız → net = added - lost."""
    passes = [
        _pass(1, sx=50, sy=50, ex=80, ey=50, completed=True),    # added
        _pass(1, sx=70, sy=50, ex=90, ey=50, completed=False),   # lost
    ]
    r = compute_player_xt(1, passes, [], minutes_played=90)
    assert r.value.xt_added > 0
    assert r.value.xt_lost > 0
    assert abs(r.value.xt_net - (r.value.xt_added - r.value.xt_lost)) < 1e-4


def test_carry_into_box_adds_xt():
    """Carry x=70'ten x=90'a → pozitif xT."""
    carries = [_carry(1, sx=70, sy=50, ex=90, ey=50)]
    r = compute_player_xt(1, [], carries, minutes_played=90)
    assert r.value.xt_added > 0


def test_per_90_normalization():
    """45 dk oynayan oyuncuda per_90 net'in 2 katı."""
    passes = [_pass(1, sx=50, sy=50, ex=80, ey=50, completed=True)]
    r = compute_player_xt(1, passes, [], minutes_played=45)
    expected_per_90 = r.value.xt_net * 2  # 45*2 = 90
    assert abs(r.value.xt_per_90 - expected_per_90) < 1e-3


def test_other_player_excluded():
    """Sadece istenen player_id sayılmalı."""
    passes = [
        _pass(1, sx=50, sy=50, ex=80, ey=50),
        _pass(2, sx=50, sy=50, ex=80, ey=50),  # farklı player
    ]
    r = compute_player_xt(1, passes, [], minutes_played=90)
    assert r.value.actions == 1


def test_audit_includes_grid_info():
    r = compute_player_xt(1, [], [], minutes_played=90)
    assert r.audit.engine == "engine.xt"
    assert r.audit.inputs["grid_x"] == 12
    assert r.audit.inputs["grid_y"] == 8


# --------------------------------------------------------------------------- #
# Team xT
# --------------------------------------------------------------------------- #


def test_team_xt_sums_player_contributions():
    passes = [
        _pass(1, sx=50, sy=50, ex=80, ey=50, team_id=10),
        _pass(2, sx=60, sy=50, ex=85, ey=50, team_id=10),
        _pass(3, sx=50, sy=50, ex=80, ey=50, team_id=99),  # different team
    ]
    r = compute_team_xt(10, passes, [], minutes_played=90)
    assert r.value.actions == 2
    assert r.value.total_xt > 0


def test_team_xt_no_passes_returns_zero():
    r = compute_team_xt(10, [], [], minutes_played=90)
    assert r.value.total_xt == 0.0
    assert r.value.actions == 0
