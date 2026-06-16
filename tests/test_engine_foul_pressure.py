"""Foul Pressure engine — takım faul biriktirme + hakem kart eşiği (I.1)."""
from __future__ import annotations

from app.engine.foul_pressure import compute_foul_pressure


def _f(team: int, minute: float, player: int | None = None) -> dict:
    """Faul event factory."""
    ev = {"team_id": team, "minute": minute}
    if player is not None:
        ev["player_id"] = player
    return ev


# --------------------------------------------------------------------------- #
# Takım-düzeyi sayım
# --------------------------------------------------------------------------- #


def test_window_count_basic():
    """Pencere içi/dışı sayım doğru."""
    # window = current 70 - 15 = [55, 70]
    events = [
        _f(22, 50.0),  # dışında
        _f(22, 58.0),  # içinde
        _f(22, 65.0),  # içinde
        _f(11, 60.0),  # bizim, içinde
    ]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0, window_min=15.0,
    ).value
    assert r.opp_fouls_total == 3
    assert r.opp_fouls_window == 2
    assert r.our_fouls_window == 1


def test_rate_per_10min_calculation():
    """rate = (window_fouls / window_min) * 10."""
    events = [_f(22, float(60 + i)) for i in range(6)]  # 6 faul, 60-65
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0, window_min=10.0,
    ).value
    # window 60-70: 6 faul, rate = 6/10*10 = 6.0
    assert r.opp_foul_rate_per_10min == 6.0


# --------------------------------------------------------------------------- #
# Ritim kırma + yığılma + yüksek kart sinyalleri
# --------------------------------------------------------------------------- #


def test_tactical_fouling_alert_when_opp_rate_high():
    """Rakip 5 faul/15dk → 3.33/10dk → tactical_fouling_alert."""
    events = [_f(22, float(60 + i)) for i in range(5)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=75.0, window_min=15.0,
    ).value
    assert r.tactical_fouling_alert is True
    assert "ritim kırma" in r.tactical_advice.lower()


def test_no_alert_when_opp_low_rate():
    """Rakip 1 faul/15dk → eşiğin altında, alert yok."""
    events = [_f(22, 65.0)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=75.0, window_min=15.0,
    ).value
    assert r.tactical_fouling_alert is False


def test_our_high_foul_alert():
    """Bizim 5 faul/15dk → savunmada zonal blok tavsiyesi."""
    events = [_f(11, float(60 + i)) for i in range(5)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=75.0, window_min=15.0,
    ).value
    assert r.our_high_foul_alert is True
    assert "zonal" in r.tactical_advice.lower()


def test_escalation_alert_window_concentration():
    """Rakip toplam fauluunun %80'i son window'da → escalation."""
    # Toplam 5: 1 erken (10. dk), 4 son window (60-65)
    events = [_f(22, 10.0)] + [_f(22, float(60 + i)) for i in range(4)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0, window_min=15.0,
    ).value
    assert r.escalation_alert is True


def test_no_escalation_when_uniform():
    """Faul rakip-eşit dağılmış → escalation yok."""
    events = [_f(22, float(10 + 15 * i)) for i in range(5)]  # 10, 25, 40, 55, 70
    r = compute_foul_pressure(
        11, 22, events, current_minute=75.0, window_min=15.0,
    ).value
    assert r.escalation_alert is False


# --------------------------------------------------------------------------- #
# Oyuncu kart riski
# --------------------------------------------------------------------------- #


def test_player_critical_yellow_plus_fouls():
    """Sarılı oyuncu 3+ faul → critical, 2. sarı yakın."""
    events = [_f(11, 60.0, player=99) for _ in range(3)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0,
        player_yellow_cards={99: 1},
    ).value
    assert len(r.player_flags) == 1
    f = r.player_flags[0]
    assert f.player_external_id == 99
    assert f.risk_level == "critical"
    assert f.has_yellow is True


def test_player_warning_no_yellow_many_fouls():
    """Kartsız oyuncu 4 faul → warning."""
    events = [_f(11, 60.0, player=42) for _ in range(4)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0,
    ).value
    assert len(r.player_flags) == 1
    assert r.player_flags[0].risk_level == "warning"
    assert r.player_flags[0].has_yellow is False


def test_player_safe_few_fouls():
    """1-2 faul + kartsız → flag yok."""
    events = [_f(11, 60.0, player=7), _f(11, 65.0, player=7)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0,
    ).value
    assert len(r.player_flags) == 0


def test_player_warning_yellow_few_fouls():
    """Sarılı + 1-2 faul → warning (henüz critical değil)."""
    events = [_f(11, 60.0, player=5)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=70.0,
        player_yellow_cards={5: 1},
    ).value
    assert len(r.player_flags) == 1
    assert r.player_flags[0].risk_level == "warning"


# --------------------------------------------------------------------------- #
# Hakem kart eşiği
# --------------------------------------------------------------------------- #


def test_referee_low_pressure():
    r = compute_foul_pressure(
        11, 22, [], current_minute=60.0, total_yellows_match=2,
    ).value
    assert r.referee_card_pressure == "low"


def test_referee_moderate_pressure():
    r = compute_foul_pressure(
        11, 22, [], current_minute=60.0, total_yellows_match=4,
    ).value
    assert r.referee_card_pressure == "moderate"


def test_referee_high_pressure_advice():
    r = compute_foul_pressure(
        11, 22, [], current_minute=70.0, total_yellows_match=7,
    ).value
    assert r.referee_card_pressure == "high"
    assert "kart eşiğinde" in r.tactical_advice.lower()


# --------------------------------------------------------------------------- #
# Boş + audit + advice fallback
# --------------------------------------------------------------------------- #


def test_empty_events_normal_advice():
    r = compute_foul_pressure(
        11, 22, [], current_minute=70.0,
    ).value
    assert r.tactical_advice == "Faul ritmi normal — standart oyun planına devam"
    assert r.opp_fouls_total == 0
    assert r.our_fouls_total == 0


def test_audit_record_complete():
    events = [_f(22, 65.0), _f(22, 68.0)]
    res = compute_foul_pressure(
        11, 22, events, current_minute=70.0, total_yellows_match=3,
    )
    a = res.audit.value
    assert "our_foul_rate_per_10min" in a
    assert "opp_foul_rate_per_10min" in a
    assert "tactical_fouling_alert" in a
    assert "referee_card_pressure" in a
    assert "tactical_advice" in a


def test_combined_signals_advice():
    """Rakip ritim kırma + hakem kart eşiği → iki sinyal birden."""
    # Rakip: 5 faul/15dk, 5/5 son window → tactical + escalation
    events = [_f(22, float(60 + i)) for i in range(5)]
    r = compute_foul_pressure(
        11, 22, events, current_minute=75.0, window_min=15.0,
        total_yellows_match=7,
    ).value
    assert r.tactical_fouling_alert is True
    assert r.escalation_alert is True
    assert r.referee_card_pressure == "high"
    # Birden fazla parça birleştirilmiş " · " ile
    assert " · " in r.tactical_advice
