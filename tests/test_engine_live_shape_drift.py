"""engine.live_shape_drift tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.live_shape_drift import compute_live_shape_drift


def _p(player: int, minute: float, sx: float, sy: float = 50) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=sx, start_y=sy, end_x=sx + 5, end_y=sy,
    )


def test_no_drift_stable_shape():
    """5 oyuncu, hepsinin pozisyonu sabit → shape_changed=False."""
    passes = []
    for player in (10, 20, 30, 40, 50):
        # Early (0-30) ve recent (50-60) aynı x'te
        for m in range(5, 28, 5):
            passes.append(_p(player, m, sx=30 + player))
        for m in range(50, 62, 2):
            passes.append(_p(player, m, sx=30 + player))
    r = compute_live_shape_drift(
        team_external_id=11, all_passes=passes, current_minute=60.0,
    ).value
    assert r.shape_changed is False


def test_formation_changed_when_multiple_players_drift():
    """5 oyuncu erkenden x=30'da, sonra x=70'e kaymış → shape_changed=True."""
    passes = []
    for player in (10, 20, 30, 40, 50):
        # Early window (0-30): 5 pas
        for m in (5, 10, 15, 20, 25):
            passes.append(_p(player, m, sx=30))
        # Recent window (50-60): 5 pas, 40 birim ileri
        for m in (51, 53, 55, 57, 59):
            passes.append(_p(player, m, sx=70))
    r = compute_live_shape_drift(
        team_external_id=11, all_passes=passes, current_minute=60.0,
    ).value
    assert r.shape_changed is True
    assert r.n_players_significant_drift >= 4


def test_individual_shift_only():
    """Sadece 1 oyuncu drift → shape_changed=False, individual_shift."""
    passes = []
    for player in (10, 20, 30, 40, 50):
        for m in (5, 10, 15, 20, 25):
            passes.append(_p(player, m, sx=30 + player))
        for m in (51, 53, 55, 57, 59):
            sx = 70 if player == 10 else 30 + player
            passes.append(_p(player, m, sx=sx))
    r = compute_live_shape_drift(
        team_external_id=11, all_passes=passes, current_minute=60.0,
    ).value
    assert r.shape_changed is False
    assert r.n_players_significant_drift == 1
    assert "Individual shift" in r.alert_text


def test_min_passes_filter():
    """Çok az pas yapan oyuncu (eşik altı) sayılmaz."""
    passes = [_p(10, 10, 50)]  # tek pas, eşik 4
    r = compute_live_shape_drift(
        team_external_id=11, all_passes=passes, current_minute=60.0,
    ).value
    assert r.n_players_analyzed == 0


def test_other_team_excluded():
    """Rakip takım pasları sayılmaz."""
    passes = []
    for player in (10, 20):
        for m in range(5, 28, 5):
            passes.append(PassEvent(
                sport="football", match_external_id=99,
                player_external_id=player, team_external_id=22,  # rakip
                minute=float(m), period=1,
                start_x=30, start_y=50, end_x=40, end_y=50,
            ))
    r = compute_live_shape_drift(
        team_external_id=11, all_passes=passes, current_minute=60.0,
    ).value
    assert r.n_players_analyzed == 0
