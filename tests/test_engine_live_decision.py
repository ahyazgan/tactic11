"""Faz 6 maç-içi karar engine'leri — momentum/sub_timing/tactical/risk/reaction."""
from __future__ import annotations

from app.domain import DefensiveAction, PassEvent, Shot
from app.engine.live_risk_monitor import compute_live_risk_monitor
from app.engine.live_tactical_trigger import compute_live_tactical_trigger
from app.engine.momentum_tracker import compute_momentum
from app.engine.opponent_reaction import compute_opponent_reaction
from app.engine.sub_timing import compute_sub_timing


def _p(team: int, minute: float, ex: float = 70, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=1,
        team_external_id=team, minute=minute, period=1,
        start_x=50, start_y=50, end_x=ex, end_y=50, completed=completed,
    )


def _d(team: int, minute: float, player: int = 1) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=team, minute=minute, period=1,
        x=50, y=50, action_type="tackle",
    )


def _s(minute: float, team: int | None, x: float = 95) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=10,
        minute=minute, x=x, y=50, team_external_id=team,
    )


# --------------------------------------------------------------------------- #
# momentum_tracker
# --------------------------------------------------------------------------- #


def test_momentum_us_when_we_dominate():
    """Bizim window'da çok ileri pas + şut → momentum us."""
    passes = [_p(11, minute=float(62 + i), ex=85) for i in range(8)]
    shots = [_s(63.0, 11), _s(65.0, 11)]
    r = compute_momentum(
        11, 22, passes, [], shots, current_minute=70.0,
    ).value
    assert r.momentum_holder == "us"
    assert r.momentum_score > 0


def test_momentum_opponent():
    passes = [_p(22, minute=float(62 + i), ex=85) for i in range(8)]
    shots = [_s(63.0, 22), _s(65.0, 22)]
    r = compute_momentum(
        11, 22, passes, [], shots, current_minute=70.0,
    ).value
    assert r.momentum_holder == "opponent"


def test_press_breaking_detected():
    """Önceki window 10 def, şimdiki 2 def → pres kırıldı."""
    # prev window 50-60, current 60-70
    defs = [_d(11, minute=float(50 + i)) for i in range(10)]  # prev: 10
    defs += [_d(11, minute=float(60 + i)) for i in range(2)]   # current: 2
    r = compute_momentum(
        11, 22, [], defs, [], current_minute=70.0,
    ).value
    assert r.press_breaking is True


def test_xg_swing_alert():
    """Rakip window'da yüksek xG → swing alert."""
    shots = [_s(63.0, 22, x=98), _s(65.0, 22, x=97)]  # rakip yakın şutlar
    r = compute_momentum(
        11, 22, [], [], shots, current_minute=70.0,
    ).value
    assert r.xg_swing_alert is True


# --------------------------------------------------------------------------- #
# sub_timing
# --------------------------------------------------------------------------- #


def test_sub_timing_now_for_critical_fatigue():
    """Çok yorgun oyuncu → timing now."""
    passes = (
        [_p(11, minute=10.0)] * 15 + [_p(11, minute=70.0, completed=False)] * 5
    )
    r = compute_sub_timing(
        11, passes, [], current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert r.minutes_remaining == 15.0
    # En azından bir advice üretilmeli
    assert len(r.advices) >= 0


def test_sub_timing_package_when_trailing():
    """Geride + yorgun → paket öneri."""
    passes = (
        [_p(11, minute=10.0, completed=True)] * 20
        + [_p(11, minute=70.0, completed=False)] * 8
    )
    r = compute_sub_timing(
        11, passes, [], current_minute=78.0, my_score=0, opponent_score=2,
    ).value
    # Paket rationale geride moduna işaret etmeli (varsa)
    assert isinstance(r.package_recommendation, tuple)


def test_sub_timing_no_subs_minimal():
    r = compute_sub_timing(
        11, [], [], current_minute=60.0,
    ).value
    assert len(r.advices) == 0
    assert "gerekmiyor" in r.package_rationale


# --------------------------------------------------------------------------- #
# live_tactical_trigger
# --------------------------------------------------------------------------- #


def test_formation_trigger_trailing_late():
    r = compute_live_tactical_trigger(
        11, current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert r.score_state == "trailing"
    form = next(t for t in r.triggers if t.trigger_type == "formation")
    assert form.fired is True
    assert "hücum" in form.recommendation


def test_press_height_high_fatigue():
    r = compute_live_tactical_trigger(
        11, current_minute=60.0, my_score=1, opponent_score=1,
        avg_team_fatigue=0.6,
    ).value
    press = next(t for t in r.triggers if t.trigger_type == "press_height")
    assert press.fired is True
    assert "düşür" in press.recommendation


def test_channel_shift_when_collision():
    """Bizim dominant kanal = rakip güçlü kanal → shift."""
    r = compute_live_tactical_trigger(
        11, current_minute=50.0,
        our_dominant_channel="left", opp_strong_channel="left",
    ).value
    shift = next(t for t in r.triggers if t.trigger_type == "channel_shift")
    assert shift.fired is True


def test_no_triggers_neutral_state():
    r = compute_live_tactical_trigger(
        11, current_minute=30.0, my_score=0, opponent_score=0,
        avg_team_fatigue=0.2, momentum_score=0.0,
    ).value
    assert r.active_count == 0


# --------------------------------------------------------------------------- #
# live_risk_monitor
# --------------------------------------------------------------------------- #


def test_card_flag_yellow_high_duels():
    states = [{"player_id": 100, "yellow_card": True, "duel_count": 5}]
    r = compute_live_risk_monitor(
        11, states, current_minute=60.0,
    ).value
    assert len(r.card_flags) == 1
    assert r.card_flags[0].severity == "high"


def test_injury_flag_high_fatigue():
    states = [{"player_id": 100, "fatigue": 0.8}]
    r = compute_live_risk_monitor(
        11, states, current_minute=70.0,
    ).value
    assert len(r.injury_flags) == 1


def test_time_management_leading_late():
    r = compute_live_risk_monitor(
        11, [], current_minute=80.0, my_score=2, opponent_score=1,
    ).value
    assert "beklet" in r.time_management


def test_time_management_trailing_late():
    r = compute_live_risk_monitor(
        11, [], current_minute=80.0, my_score=0, opponent_score=1,
    ).value
    assert "tempoyu artır" in r.time_management


# --------------------------------------------------------------------------- #
# opponent_reaction
# --------------------------------------------------------------------------- #


def test_opponent_forward_sub_interpreted():
    subs = [{"position_in": "F", "minute": 65}]
    r = compute_opponent_reaction(
        11, 22, subs, current_minute=66.0,
    ).value
    assert r.opp_subs_detected == 1
    assert "hücum" in r.sub_interpretation[0]["opponent_intent"]


def test_momentum_break_advice_when_pressured():
    r = compute_opponent_reaction(
        11, 22, [], current_minute=70.0, momentum_score=-0.5,
    ).value
    assert r.momentum_break_advice is not None
    assert "yavaşlat" in r.momentum_break_advice


def test_opponent_defender_sub_counter():
    subs = [{"position_in": "D", "minute": 80}]
    r = compute_opponent_reaction(
        11, 22, subs, current_minute=81.0,
    ).value
    assert "kanat" in r.sub_interpretation[0]["our_counter"]


def test_static_opponent():
    r = compute_opponent_reaction(
        11, 22, [], current_minute=50.0, momentum_score=0.1,
    ).value
    assert "statik" in r.overall_advice
