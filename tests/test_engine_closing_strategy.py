"""Closing Strategy engine — kapanış reçetesi + risk/getiri eşiği."""
from __future__ import annotations

from app.engine.closing_strategy import compute_closing_strategy

# --------------------------------------------------------------------------- #
# score_state + closing_phase sınıflandırma
# --------------------------------------------------------------------------- #


def test_early_phase_low_urgency():
    """60. dk öncesi → kapanış reçetesi devreye girmez."""
    r = compute_closing_strategy(
        11, current_minute=30.0, my_score=0, opponent_score=0,
    ).value
    assert r.closing_phase == "early"
    assert r.urgency_level == "low"
    assert r.recipe.tempo == "normal"
    assert "değil" in r.recipe.extra_note  # "Kapanış evresi değil"


def test_phase_boundaries():
    """60-75 mid, 75-90 late, 90+ stoppage."""
    assert compute_closing_strategy(
        11, current_minute=70.0, my_score=0, opponent_score=0,
    ).value.closing_phase == "mid"
    assert compute_closing_strategy(
        11, current_minute=82.0, my_score=0, opponent_score=0,
    ).value.closing_phase == "late"
    assert compute_closing_strategy(
        11, current_minute=93.0, my_score=0, opponent_score=0,
    ).value.closing_phase == "stoppage"


def test_score_state_classification():
    """diff >= 3 big_lead, 1-2 leading, 0 level, -1 to -2 trailing, <=-3 big_deficit."""
    states = {
        (3, 0): "big_lead",
        (2, 0): "leading",
        (1, 0): "leading",
        (1, 1): "level",
        (0, 1): "trailing",
        (0, 2): "trailing",
        (0, 3): "big_deficit",
    }
    for (m, o), expected in states.items():
        r = compute_closing_strategy(
            11, current_minute=80.0, my_score=m, opponent_score=o,
        ).value
        assert r.score_state == expected, f"({m}-{o}) → {r.score_state}, beklenen {expected}"


# --------------------------------------------------------------------------- #
# Kapanış reçetesi — somut taktik (state × phase matrisi)
# --------------------------------------------------------------------------- #


def test_recipe_leading_late_lock_down():
    """Önde 1-0, 80. dk → tempo düşür + alçal + savunmacı ikame."""
    r = compute_closing_strategy(
        11, current_minute=80.0, my_score=1, opponent_score=0,
    ).value
    assert r.recipe.tempo == "düşür"
    assert r.recipe.positioning == "alçal"
    assert r.recipe.sub_priority == "savunmacı"
    assert r.recipe.set_pieces == "alma"


def test_recipe_trailing_late_all_out():
    """Geride 0-1, 82. dk → agresif tempo + all-out + hücumcu."""
    r = compute_closing_strategy(
        11, current_minute=82.0, my_score=0, opponent_score=1,
    ).value
    assert r.recipe.tempo == "agresif"
    assert r.recipe.positioning == "all-out"
    assert r.recipe.sub_priority == "hücumcu"
    assert r.recipe.set_pieces == "risk-al"


def test_recipe_stoppage_trailing_emergency():
    """Geride uzatma → acil + her şey."""
    r = compute_closing_strategy(
        11, current_minute=92.0, my_score=0, opponent_score=1,
    ).value
    assert r.recipe.tempo == "acil"
    assert r.recipe.set_pieces == "her şey"
    assert "GK" in r.recipe.extra_note or "kale" in r.recipe.extra_note.lower()


def test_recipe_level_late_push_for_win():
    """Berabere 1-1, 80. dk → tempo yükselt + hücumcu ikame."""
    r = compute_closing_strategy(
        11, current_minute=80.0, my_score=1, opponent_score=1,
    ).value
    assert r.recipe.tempo == "yükselt"
    assert r.recipe.sub_priority == "hücumcu"


def test_recipe_big_lead_late_protect_stars():
    """Önde 3-0, 80. dk → yıldızları çek + maçı öldür."""
    r = compute_closing_strategy(
        11, current_minute=80.0, my_score=3, opponent_score=0,
    ).value
    assert r.recipe.tempo == "düşür"
    assert r.recipe.sub_priority == "yıldızı çek"


def test_recipe_negative_momentum_extra_defensive():
    """Önde ama rakip baskılıyor → extra savunmacı note."""
    r = compute_closing_strategy(
        11, current_minute=80.0, my_score=1, opponent_score=0,
        momentum_score=-0.5,
    ).value
    assert "rakip baskısı" in r.recipe.extra_note


# --------------------------------------------------------------------------- #
# Risk/getiri eşiği
# --------------------------------------------------------------------------- #


def test_risk_take_when_trailing_late():
    """1 geride + 80. dk → riski al."""
    r = compute_closing_strategy(
        11, current_minute=82.0, my_score=0, opponent_score=1,
    ).value
    assert r.risk_reward.take_risk is True
    assert "geride" in r.risk_reward.rationale.lower()


def test_risk_take_when_big_deficit():
    """2 geride + 65. dk → tam risk (eşik 60)."""
    r = compute_closing_strategy(
        11, current_minute=65.0, my_score=0, opponent_score=2,
    ).value
    assert r.risk_reward.take_risk is True
    assert "tam risk" in r.risk_reward.rationale.lower()


def test_risk_lock_when_leading_late():
    """Önde 1-0 + 82. dk → riski azalt."""
    r = compute_closing_strategy(
        11, current_minute=82.0, my_score=1, opponent_score=0,
    ).value
    assert r.risk_reward.take_risk is False
    assert "kontra" in r.risk_reward.rationale.lower()


def test_risk_none_in_early_phase():
    """Erken evre → risk eşiği fırlamamış."""
    r = compute_closing_strategy(
        11, current_minute=30.0, my_score=0, opponent_score=1,
    ).value
    assert r.risk_reward.take_risk is False
    assert r.risk_reward.threshold_breached == "none"


def test_risk_level_last_minutes():
    """Berabere + 87. dk → temkinli risk."""
    r = compute_closing_strategy(
        11, current_minute=87.0, my_score=1, opponent_score=1,
    ).value
    assert r.risk_reward.take_risk is True
    assert "kontra" in r.risk_reward.rationale.lower()


# --------------------------------------------------------------------------- #
# Urgency + key_message + audit
# --------------------------------------------------------------------------- #


def test_urgency_critical_in_stoppage_trailing():
    r = compute_closing_strategy(
        11, current_minute=92.0, my_score=0, opponent_score=1,
    ).value
    assert r.urgency_level == "critical"


def test_urgency_high_when_leading_late_under_pressure():
    """Önde ama momentum negatif + late → high."""
    r = compute_closing_strategy(
        11, current_minute=82.0, my_score=1, opponent_score=0,
        momentum_score=-0.5,
    ).value
    assert r.urgency_level == "high"


def test_key_message_contains_state_and_phase():
    r = compute_closing_strategy(
        11, current_minute=82.0, my_score=0, opponent_score=1,
    ).value
    assert "Geride" in r.key_message
    assert "son 15 dk" in r.key_message


def test_audit_record_complete():
    """Audit value tüm önemli alanları içeriyor."""
    res = compute_closing_strategy(
        11, current_minute=80.0, my_score=1, opponent_score=1,
    )
    audit_val = res.audit.value
    assert "score_state" in audit_val
    assert "closing_phase" in audit_val
    assert "recipe" in audit_val
    assert "risk_reward" in audit_val
    assert audit_val["recipe"]["tempo"] in (
        "düşür", "normal", "yükselt", "agresif", "acil",
    )


def test_minutes_remaining_calculation():
    r = compute_closing_strategy(
        11, current_minute=80.0, my_score=0, opponent_score=0,
        match_total_minutes=90.0,
    ).value
    assert r.minutes_remaining == 10.0
    r2 = compute_closing_strategy(
        11, current_minute=95.0, my_score=0, opponent_score=0,
        match_total_minutes=90.0,
    ).value
    assert r2.minutes_remaining == 0.0
