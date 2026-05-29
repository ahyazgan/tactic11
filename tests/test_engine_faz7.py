"""Faz 7 maç-içi karar engine'leri — spatial/matchup/set_piece/friction/referee/score-time."""
from __future__ import annotations

from app.domain import DefensiveAction, PassEvent
from app.engine.game_friction import compute_game_friction
from app.engine.live_matchup import compute_live_matchup
from app.engine.referee_context import compute_referee_context
from app.engine.score_time_matrix import compute_score_time_matrix
from app.engine.set_piece_timing import compute_set_piece_timing
from app.engine.spatial_control import compute_spatial_control


def _p(team: int, minute: float, ex: float = 70, ey: float = 50,
       pid: int = 1, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=pid,
        team_external_id=team, minute=minute, period=2,
        start_x=50, start_y=50, end_x=ex, end_y=ey, completed=completed,
    )


def _d(team: int, minute: float, x: float = 50, y: float = 50,
       pid: int = 1, ok: bool = True, at: str = "tackle") -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=pid,
        team_external_id=team, minute=minute, period=2,
        x=x, y=y, action_type=at, successful=ok,
    )


# --------------------------------------------------------------------------- #
# F — spatial_control
# --------------------------------------------------------------------------- #


def test_spatial_gap_between_lines():
    """Zone-14'e 4 tamamlanan pasımız, rakip 0 def → boşluk."""
    passes = [_p(11, 60 + i, ex=75, ey=50) for i in range(4)]
    r = compute_spatial_control(11, 22, passes, [], current_minute=65).value
    assert r.gap_between_lines is True
    assert r.our_zone14_passes >= 3
    assert any("BOŞLUK" in a for a in r.alerts)


def test_spatial_no_gap_when_opponent_present():
    """Rakip zone-14'te def yapıyorsa boşluk yok."""
    passes = [_p(11, 60 + i, ex=75, ey=50) for i in range(4)]
    # rakip aynı zonda def (100-x => 75 => x=25), y merkez
    defs = [_d(22, 60 + i, x=25, y=50) for i in range(3)]
    r = compute_spatial_control(11, 22, passes, defs, current_minute=65).value
    assert r.gap_between_lines is False


def test_spatial_numerical_superiority_flank():
    """Sol kanatta bizim katılım çok, rakip az → üstünlük sol."""
    passes = [_p(11, 60 + i * 0.2, ex=70, ey=15) for i in range(5)]  # left
    defs = [_d(22, 60, y=15)]
    r = compute_spatial_control(11, 22, passes, defs, current_minute=65).value
    assert r.superiority_flank == "left"


def test_spatial_narrow_shape():
    """Tüm paslar merkez bandında → darlık."""
    passes = [_p(11, 60 + i * 0.1, ex=70, ey=50) for i in range(6)]
    r = compute_spatial_control(11, 22, passes, [], current_minute=65).value
    assert r.shape_state == "narrow"


# --------------------------------------------------------------------------- #
# G — live_matchup
# --------------------------------------------------------------------------- #


def test_matchup_struggling_defender():
    """#7 oyuncumuz 5 düellodan 4 kaybetti → flag + öneri."""
    defs = [_d(11, 60 + i * 0.1, pid=7, ok=False) for i in range(4)]
    defs += [_d(11, 61, pid=7, ok=True)]
    r = compute_live_matchup(11, 22, [], defs, current_minute=65).value
    assert r.struggling_defender is not None
    assert r.struggling_defender.player_external_id == 7
    assert r.struggling_defender.lost == 4


def test_matchup_hot_opponent():
    """Rakip #99 her topa giriyor → sıcak el."""
    passes = [_p(22, 60 + i * 0.1, pid=99) for i in range(8)]
    r = compute_live_matchup(11, 22, passes, [], current_minute=65).value
    assert r.hot_opponent is not None
    assert r.hot_opponent.player_external_id == 99


def test_matchup_feed_star_when_quiet():
    """Yıldız son window'da 0 dokunuş → besle uyarısı."""
    passes = [_p(11, 60 + i * 0.1, pid=5) for i in range(6)]
    r = compute_live_matchup(11, 22, passes, [], current_minute=65,
                             star_player_id=10).value
    assert r.feed_star is True
    assert r.star_touches == 0


def test_matchup_star_active_no_feed():
    passes = [_p(11, 60 + i * 0.1, pid=10) for i in range(6)]
    r = compute_live_matchup(11, 22, passes, [], current_minute=65,
                             star_player_id=10).value
    assert r.feed_star is False


# --------------------------------------------------------------------------- #
# H — set_piece_timing
# --------------------------------------------------------------------------- #


def test_set_piece_corner_opportunity():
    r = compute_set_piece_timing(
        11, current_minute=70, set_piece_won="corner",
        opponent_weak_zones=["far_post"],
    ).value
    assert r.opportunity is not None
    assert r.opportunity.target_zone == "far_post"


def test_set_piece_penalty_taker_unfit():
    r = compute_set_piece_timing(
        11, current_minute=70,
        penalty_taker={"player_id": 9, "fatigue": 0.9, "recent_accuracy": 0.5},
    ).value
    assert r.penalty_status is not None
    assert r.penalty_status.fit_to_take is False


def test_set_piece_penalty_taker_fit():
    r = compute_set_piece_timing(
        11, current_minute=70,
        penalty_taker={"player_id": 9, "fatigue": 0.3, "recent_accuracy": 0.9},
    ).value
    assert r.penalty_status.fit_to_take is True


# --------------------------------------------------------------------------- #
# I — game_friction
# --------------------------------------------------------------------------- #


def test_friction_foul_hotspot():
    r = compute_game_friction(
        11, 22, [], current_minute=65,
        opponent_foul_zones=["left_wing", "left_wing", "center"],
    ).value
    assert r.foul_hotspot is not None
    assert r.foul_hotspot.zone == "left_wing"
    assert r.foul_hotspot.count == 2


def test_friction_offside_trap_risk():
    """Rakip yüksek + senkron hat (100-x≈70, dar) → ofsayt tuzağı."""
    defs = [_d(22, 60 + i * 0.2, x=30, y=50 + (i % 2)) for i in range(6)]
    r = compute_game_friction(11, 22, defs, current_minute=65).value
    assert r.offside_trap_risk is True
    assert r.opp_line_height >= 65.0


def test_friction_no_trap_low_line():
    """Rakip alçak hat → tuzak yok."""
    defs = [_d(22, 60 + i * 0.2, x=85, y=50) for i in range(6)]
    r = compute_game_friction(11, 22, defs, current_minute=65).value
    assert r.offside_trap_risk is False


# --------------------------------------------------------------------------- #
# J — referee_context
# --------------------------------------------------------------------------- #


def test_referee_strict():
    r = compute_referee_context(11, current_minute=50, cards_per_game=5.0).value
    assert r.strict_referee is True


def test_referee_advantage_window():
    r = compute_referee_context(
        11, current_minute=50, cards_per_game=2.0,
        opponent_card_edge_players=[{"player_id": 4, "position_zone": "sağ bek"}],
    ).value
    assert r.strict_referee is False
    assert len(r.advantage_targets) == 1
    assert r.advantage_targets[0].player_external_id == 4


# --------------------------------------------------------------------------- #
# K — score_time_matrix
# --------------------------------------------------------------------------- #


def test_score_time_leading_late_see_out():
    r = compute_score_time_matrix(
        11, current_minute=86, my_score=1, opponent_score=0,
    ).value
    assert r.score_state == "leading"
    assert r.posture == "see_out"
    assert "köşeye" in r.closing_recipe


def test_score_time_trailing_late_all_out():
    r = compute_score_time_matrix(
        11, current_minute=88, my_score=0, opponent_score=1,
    ).value
    assert r.score_state == "trailing"
    assert r.posture == "all_out"


def test_score_time_drawing_must_win_all_out():
    r = compute_score_time_matrix(
        11, current_minute=89, my_score=0, opponent_score=0, must_win=True,
    ).value
    assert r.posture == "all_out"
    assert r.must_win is True


def test_score_time_draw_enough_see_out():
    r = compute_score_time_matrix(
        11, current_minute=80, my_score=0, opponent_score=0,
        draw_is_enough=True,
    ).value
    assert r.posture == "see_out"
    assert r.draw_acceptable is True
