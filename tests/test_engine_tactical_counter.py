"""Tactical Counter — (rakip × bizim) matrix advisor."""
from __future__ import annotations

from app.engine.tactical_counter import compute_counter_advice


def test_specific_matchup_klopp_vs_pep():
    r = compute_counter_advice(
        opponent_style="klopp_press", our_style="pep_possession",
    ).value
    assert len(r.advices) >= 3
    texts = " ".join(a.text.lower() for a in r.advices)
    assert "gk" in texts or "geri" in texts or "derinlik" in texts


def test_specific_matchup_klopp_vs_bvb_counter():
    r = compute_counter_advice(
        opponent_style="klopp_press", our_style="bvb_counter",
    ).value
    texts = " ".join(a.text.lower() for a in r.advices)
    assert "dik koş" in texts or "kontra" in texts


def test_atletico_compact_universal_advice():
    """opp=atletico_compact + our=any → universal advice fallback."""
    r = compute_counter_advice(
        opponent_style="atletico_compact", our_style="ten_hag_modern_pos",
    ).value
    texts = " ".join(a.text.lower() for a in r.advices)
    # Universal "set-piece koreografi" + "uzaktan şut" beklenir
    assert "set-piece" in texts or "ikinci top" in texts


def test_advice_focus_diversity():
    """Bir matchup'ta farklı focus türleri gelir (shape/transition/press)."""
    r = compute_counter_advice(
        opponent_style="klopp_press", our_style="pep_possession",
    ).value
    assert len(r.focuses) >= 2


def test_unknown_styles_fallback_to_any():
    r = compute_counter_advice(
        opponent_style="unknown_arch", our_style="another_unknown",
    ).value
    # (any, any) fallback → en azından 1 satır gelir
    assert len(r.advices) >= 1


def test_max_advice_cap():
    r = compute_counter_advice(
        opponent_style="klopp_press", our_style="pep_possession",
        max_advice=2,
    ).value
    assert len(r.advices) <= 2


def test_no_duplicate_advice_text():
    r = compute_counter_advice(
        opponent_style="atletico_compact", our_style="any",
    ).value
    texts = [a.text for a in r.advices]
    assert len(texts) == len(set(texts))


def test_audit_complete():
    res = compute_counter_advice(
        opponent_style="klopp_press", our_style="bvb_counter",
    )
    a = res.audit.value
    assert "opponent_style" in a
    assert "our_style" in a
    assert "advice_count" in a
    assert "focuses" in a
