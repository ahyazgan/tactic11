"""Context pipeline — yeni 3 engine'in (closing/foul/star_feed) sinyallere
çevrilmesi ve context_engine'in tek karara indirgemesi."""
from __future__ import annotations

from app.api.context_pipeline import build_candidates
from app.engine.context_engine import compute_context


def _win() -> dict[str, int]:
    return {"passes": 50, "defs": 20, "shots": 5}


# --------------------------------------------------------------------------- #
# closing_strategy → CandidateSignal
# --------------------------------------------------------------------------- #


def test_closing_strategy_high_urgency_fires():
    """urgency=high → fired + correct theme."""
    out = {
        "closing_strategy": {
            "urgency_level": "high",
            "key_message": "Geride · son 15 dk → agresif",
            "recipe": {"tempo": "agresif", "sub_priority": "hücumcu"},
            "risk_reward": {"take_risk": True},
        },
    }
    cands = build_candidates(out, current_minute=82.0, win=_win())
    cs = [c for c in cands if c.key == "closing_strategy"]
    assert len(cs) == 1
    assert cs[0].fired is True
    assert cs[0].signal_type == "closing"
    assert cs[0].urgency >= 0.8


def test_closing_strategy_low_urgency_no_fire():
    """urgency=low + take_risk=False → fire etme."""
    out = {
        "closing_strategy": {
            "urgency_level": "low",
            "key_message": "Berabere · erken evre",
            "recipe": {"tempo": "normal", "sub_priority": "yok"},
            "risk_reward": {"take_risk": False},
        },
    }
    cands = build_candidates(out, current_minute=30.0, win=_win())
    cs = [c for c in cands if c.key == "closing_strategy"]
    assert cs == []  # low + no risk → fire etmedi


def test_closing_strategy_take_risk_fires_even_if_moderate():
    """urgency=moderate ama risk eşiği fırlamış → yine fire."""
    out = {
        "closing_strategy": {
            "urgency_level": "moderate",
            "key_message": "Geride · mid evre",
            "recipe": {"tempo": "yükselt", "sub_priority": "hücumcu"},
            "risk_reward": {"take_risk": True},
        },
    }
    cands = build_candidates(out, current_minute=65.0, win=_win())
    cs = [c for c in cands if c.key == "closing_strategy"]
    assert len(cs) == 1
    assert cs[0].fired is True


# --------------------------------------------------------------------------- #
# foul_pressure → CandidateSignal
# --------------------------------------------------------------------------- #


def test_foul_pressure_tactical_fouling_fires():
    """tactical_fouling_alert → fired."""
    out = {
        "foul_pressure": {
            "tactical_fouling_alert": True,
            "our_high_foul_alert": False,
            "referee_card_pressure": "moderate",
            "player_flags": [],
            "tactical_advice": "Rakip ritim kırma fauluyor — hızlı restart",
            "our_fouls_window": 1,
            "opp_fouls_window": 5,
        },
    }
    cands = build_candidates(out, current_minute=75.0, win=_win())
    fp = [c for c in cands if c.key == "foul_pressure"]
    assert len(fp) == 1
    assert fp[0].signal_type == "friction"
    assert "ritim kırma" in fp[0].headline.lower()


def test_foul_pressure_critical_player_higher_urgency():
    """Critical player flag → urgency 0.85+."""
    out = {
        "foul_pressure": {
            "tactical_fouling_alert": False,
            "our_high_foul_alert": False,
            "referee_card_pressure": "low",
            "player_flags": [{"player_id": 99, "risk_level": "critical"}],
            "tactical_advice": "Oyuncu 99 kritik",
            "our_fouls_window": 3,
            "opp_fouls_window": 1,
        },
    }
    cands = build_candidates(out, current_minute=70.0, win=_win())
    fp = [c for c in cands if c.key == "foul_pressure"]
    assert len(fp) == 1
    assert fp[0].urgency >= 0.85


def test_foul_pressure_normal_no_fire():
    """Hiçbir alert yok → fire etme."""
    out = {
        "foul_pressure": {
            "tactical_fouling_alert": False,
            "our_high_foul_alert": False,
            "referee_card_pressure": "low",
            "player_flags": [],
            "tactical_advice": "Normal",
            "our_fouls_window": 0, "opp_fouls_window": 0,
        },
    }
    cands = build_candidates(out, current_minute=60.0, win=_win())
    assert [c for c in cands if c.key == "foul_pressure"] == []


# --------------------------------------------------------------------------- #
# star_feed → CandidateSignal
# --------------------------------------------------------------------------- #


def test_star_feed_starved_fires_high_urgency():
    """starved → fired + urgency 0.75."""
    out = {
        "star_feed": {
            "involvement_state": "starved",
            "suggested_action": "ON",
            "tactical_advice": "Yıldız top almıyor — dik pas hattı kur",
            "team_passes_window": 25,
            "pass_share_pct": 2.0,
        },
    }
    cands = build_candidates(out, current_minute=65.0, win=_win())
    sf = [c for c in cands if c.key == "star_feed"]
    assert len(sf) == 1
    assert sf[0].signal_type == "feed"
    assert sf[0].urgency == 0.75
    assert sf[0].detail["suggested_action"] == "ON"


def test_star_feed_balanced_no_fire():
    """balanced → fire etme (normal)."""
    out = {
        "star_feed": {
            "involvement_state": "balanced",
            "suggested_action": "OK",
            "tactical_advice": "Normal",
            "team_passes_window": 20,
            "pass_share_pct": 15.0,
        },
    }
    cands = build_candidates(out, current_minute=65.0, win=_win())
    assert [c for c in cands if c.key == "star_feed"] == []


# --------------------------------------------------------------------------- #
# Orkestra: 3 yeni sinyal context_engine'de tek karar üretir
# --------------------------------------------------------------------------- #


def test_orchestra_picks_highest_priority():
    """Çakışan sinyallerden en yüksek priority primary olur."""
    out = {
        "closing_strategy": {
            "urgency_level": "critical",
            "key_message": "Geride · uzatma → acil",
            "recipe": {"tempo": "acil", "sub_priority": "hücumcu"},
            "risk_reward": {"take_risk": True},
        },
        "star_feed": {
            "involvement_state": "starved",
            "suggested_action": "ON",
            "tactical_advice": "Yıldız aç",
            "team_passes_window": 25, "pass_share_pct": 2.0,
        },
    }
    cands = build_candidates(out, current_minute=92.0, win=_win())
    decision = compute_context(
        cands, current_minute=92.0, score_state="trailing",
    ).value
    assert decision.primary is not None
    # critical urgency 0.95 → closing_strategy primary olmalı
    assert decision.primary.theme == "manage_game"
    assert "uzatma" in decision.primary.headline or "acil" in decision.primary.headline


def test_orchestra_themes_grouped_correctly():
    """foul_pressure + closing_strategy aynı tema (manage_game) → ikincil dışlanır."""
    out = {
        "closing_strategy": {
            "urgency_level": "high",
            "key_message": "Geride · son 15 dk",
            "recipe": {"tempo": "agresif", "sub_priority": "hücumcu"},
            "risk_reward": {"take_risk": True},
        },
        "foul_pressure": {
            "tactical_fouling_alert": True,
            "our_high_foul_alert": False,
            "referee_card_pressure": "high",
            "player_flags": [],
            "tactical_advice": "Rakip ritim kırma + hakem kart eşiğinde",
            "our_fouls_window": 1, "opp_fouls_window": 5,
        },
        "star_feed": {
            "involvement_state": "starved",
            "suggested_action": "ON",
            "tactical_advice": "Yıldız aç",
            "team_passes_window": 25, "pass_share_pct": 2.0,
        },
    }
    cands = build_candidates(out, current_minute=82.0, win=_win())
    decision = compute_context(
        cands, current_minute=82.0, score_state="trailing",
    ).value
    assert decision.primary is not None
    # Manage_game tema bir kere; star_feed (adjust_shape) farklı temada → secondary
    secondary_themes = [s.theme for s in decision.secondary]
    assert "adjust_shape" in secondary_themes  # star_feed
