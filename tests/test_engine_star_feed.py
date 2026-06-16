"""Star Feed engine — yıldız beslemesi monitörü (G.3)."""
from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.star_feed import compute_star_feed


def _p(
    team: int, minute: float, player: int = 1,
    sx: float = 50, sy: float = 50, ex: float = 70, ey: float = 50,
    completed: bool = True,
) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey, completed=completed,
    )


def _s(team: int, minute: float, player: int = 1) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=minute, x=95, y=50,
    )


# --------------------------------------------------------------------------- #
# Pass share + involvement_state sınıflandırma
# --------------------------------------------------------------------------- #


def test_starved_no_passes_in_window():
    """Yıldız son pencerede 0 pas → starved, ON."""
    # 30 takım pası, 0 yıldız
    passes = [_p(11, float(60 + i % 10), player=2) for i in range(30)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.star_passes_window == 0
    assert r.involvement_state == "starved"
    assert r.suggested_action == "ON"
    assert "HİÇ pas" in r.tactical_advice


def test_balanced_share():
    """Yıldız takım pasının %15'i → balanced."""
    # 17 takım pası + 3 yıldız (3/20 = 15%), hepsi window içinde (60-65)
    passes = [_p(11, 60.0 + (i % 5), player=2) for i in range(17)] + \
             [_p(11, 60.0 + i, player=99) for i in range(3)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.pass_share_pct == 15.0
    assert r.involvement_state == "balanced"
    assert r.suggested_action == "OK"


def test_underfed_share():
    """Yıldız takım pasının %5-10 arası → underfed, NUDGE."""
    # 18 takım pası, 2 yıldız (2/20 = 10% → underfed sınırı tam, ama < 10 olmalı)
    # 19 + 1 → 5%
    passes = [_p(11, 60.0, player=2) for _ in range(19)] + \
             [_p(11, 60.0, player=99)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.pass_share_pct == 5.0
    assert r.involvement_state == "underfed"
    assert r.suggested_action == "NUDGE"


def test_wellfed_share_overload():
    """Yıldız %20+ pas → well-fed, OVERLOAD."""
    # 12 takım, 8 yıldız (8/20 = 40%)
    passes = [_p(11, 60.0, player=2) for _ in range(12)] + \
             [_p(11, 60.0, player=99) for _ in range(8)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.involvement_state == "well-fed"
    assert r.suggested_action == "OVERLOAD"
    assert "yorgunluk" in r.tactical_advice.lower()


# --------------------------------------------------------------------------- #
# Final-third payı tavsiyeyi değiştiriyor
# --------------------------------------------------------------------------- #


def test_balanced_but_orta_saha_advice():
    """Balanced + final-third < %25 → 'son üçte buluşmayı artır' uyarısı."""
    # Yıldız 3 pas, hepsi orta sahada (start_x=50, FINAL_THIRD_X=66)
    passes = [_p(11, 60.0, player=2) for _ in range(17)] + \
             [_p(11, 60.0 + i, player=99, sx=50) for i in range(3)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.involvement_state == "balanced"
    assert r.final_third_share_pct == 0.0
    assert "son üçte" in r.tactical_advice.lower()


def test_final_third_share_calculation():
    """Yıldız 4 pas, 2'si son üçte → %50 share."""
    passes = [_p(11, 60.0 + i, player=99, sx=70) for i in range(2)] + \
             [_p(11, 65.0 + i, player=99, sx=40) for i in range(2)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.final_third_passes == 2
    assert r.final_third_share_pct == 50.0


# --------------------------------------------------------------------------- #
# xT katkısı
# --------------------------------------------------------------------------- #


def test_star_xt_contribution_positive():
    """Yıldızın ileri pas atması xT pozitif katkı verir."""
    # Yıldız 50→90 ileri pas (xT pozitif)
    passes = [_p(11, 60.0, player=99, sx=50, ex=90)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.star_xt_window > 0.0


def test_xt_share_calculation():
    """Yıldız tek pas atmış → xt_share %100."""
    passes = [_p(11, 60.0, player=99, sx=50, ex=85)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    # Yıldız tek pas, takım = yıldız + diğerleri yok → %100
    assert r.star_xt_share_pct == 100.0


# --------------------------------------------------------------------------- #
# Shots dahil + touches_per_10min
# --------------------------------------------------------------------------- #


def test_shots_count_as_touches():
    """Şutlar touches_per_10min'a dahil (window [65, 75])."""
    passes = [_p(11, 66.0, player=99), _p(11, 70.0, player=99)]
    shots = [_s(11, 67.0, player=99), _s(11, 72.0, player=99)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes, shots=shots,
        current_minute=75.0, window_min=10.0,
    ).value
    assert r.star_shots_window == 2
    assert r.star_passes_window == 2
    # 2 pas + 2 şut = 4 dokunma, 10 dk → 4.0/10min
    assert r.star_touches_per_10min == 4.0


# --------------------------------------------------------------------------- #
# Window dışı sayım
# --------------------------------------------------------------------------- #


def test_passes_outside_window_excluded():
    """Window dışı paslar sayılmaz."""
    passes = [_p(11, 30.0, player=99), _p(11, 65.0, player=99)]
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.star_passes_total == 2
    assert r.star_passes_window == 1


def test_opponent_passes_excluded():
    """Rakip pasları takım sayımına dahil değil."""
    passes = [_p(22, 60.0, player=99)]  # rakip oyuncusu (ama 99 bizimkinin id'si değil)
    r = compute_star_feed(
        11, star_player_id=99, passes=passes,
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.team_passes_window == 0
    assert r.star_passes_window == 0


# --------------------------------------------------------------------------- #
# Audit + edge case
# --------------------------------------------------------------------------- #


def test_audit_record_complete():
    res = compute_star_feed(
        11, star_player_id=99, passes=[_p(11, 60.0, player=99)],
        current_minute=75.0,
    )
    a = res.audit.value
    assert "involvement_state" in a
    assert "pass_share_pct" in a
    assert "tactical_advice" in a
    assert "suggested_action" in a


def test_no_team_passes_returns_starved():
    """Hiç pas yok → division-by-zero olmadan starved."""
    r = compute_star_feed(
        11, star_player_id=99, passes=[],
        current_minute=75.0, window_min=15.0,
    ).value
    assert r.pass_share_pct == 0.0
    assert r.involvement_state == "starved"
