"""Concept Recognizer — taktiksel konsept tespit motoru testleri."""
from __future__ import annotations

from app.engine.concept_recognizer import compute_active_concepts, load_concepts


def test_kb_loads_with_min_30_concepts():
    """YAML KB en az 30 konsept içermeli."""
    concepts = load_concepts()
    assert len(concepts) >= 30
    # Her konsept zorunlu alanlar
    for c in concepts:
        assert "name" in c
        assert "label" in c
        assert "family" in c
        assert "definition" in c


def test_no_active_concepts_when_signals_missing():
    """Snapshot boş → aktif konsept yok."""
    r = compute_active_concepts({}, current_minute=60.0).value
    assert len(r.opponent_concepts) == 0
    assert len(r.our_concepts) == 0
    assert "yok" in r.summary.lower()


def test_gegenpressing_recognized_from_opp_signals():
    """Düşük opp_ppda + yüksek press_height → gegenpressing aktif."""
    snap = {"opp_ppda": 7.5, "opp_press_height": 0.7}
    r = compute_active_concepts(snap, current_minute=60.0).value
    names = [c.name for c in r.opponent_concepts]
    assert "gegenpressing" in names
    # Counter advice da üretilmiş olmalı
    assert any("üçüncü oyuncu" in a.lower() or "geri pas" in a.lower()
               for a in r.counter_advice)


def test_low_block_recognized():
    """Düşük field_tilt + düşük press_height → low_block_5_4_1."""
    snap = {"opp_field_tilt_pct": 30.0, "opp_press_height": 0.25}
    r = compute_active_concepts(snap, current_minute=70.0).value
    assert any(c.name == "low_block_5_4_1" for c in r.opponent_concepts)


def test_park_the_bus_our_perspective():
    """Önde + son dakikalar + bizim → park_the_bus bizim perspective."""
    snap = {"my_score_diff": 1, "current_minute": 88}
    r = compute_active_concepts(snap, current_minute=88.0).value
    our_names = [c.name for c in r.our_concepts]
    assert "park_the_bus" in our_names
    # Counter advice bunlarda olmasa da olur; "our" perspective.


def test_high_line_offside_counter_advice():
    """Yüksek line → counter listede 'dik koşu' ipucu."""
    snap = {"opp_high_line_risk": 0.8}
    r = compute_active_concepts(snap, current_minute=70.0).value
    assert any("dik koşu" in a or "long ball" in a.lower()
               for a in r.counter_advice)


def test_multiple_concepts_aggregated():
    """Hem rakip gegenpressing hem yüksek-line → 2+ konsept aktif."""
    snap = {
        "opp_ppda": 8.0,
        "opp_press_height": 0.7,
        "opp_high_line_risk": 0.8,
    }
    r = compute_active_concepts(snap, current_minute=60.0).value
    assert len(r.opponent_concepts) >= 2


def test_families_seen_listed():
    snap = {"opp_ppda": 7.5, "opp_press_height": 0.7}
    r = compute_active_concepts(snap, current_minute=60.0).value
    assert "pressing" in r.families_seen


def test_counter_advice_limited_to_6():
    """6'dan fazla counter advice tek panele sığmaz."""
    snap = {
        "opp_ppda": 7.5, "opp_press_height": 0.7,
        "opp_high_line_risk": 0.8, "opp_counter_threat": 0.7,
        "opp_direct_play_pct": 35,
    }
    r = compute_active_concepts(snap, current_minute=60.0).value
    assert len(r.counter_advice) <= 6


def test_audit_complete():
    snap = {"opp_ppda": 7.5, "opp_press_height": 0.7}
    res = compute_active_concepts(snap, current_minute=60.0)
    a = res.audit.value
    assert "opp_concepts" in a
    assert "families" in a
    assert "summary" in a


def test_string_op_eq_works_for_bool():
    """trigger_signals'da == operatörü bool için çalışır."""
    snap = {"tactical_fouling_alert": True}
    r = compute_active_concepts(snap, current_minute=60.0).value
    # Prefix opp_ yok → "us" perspective; her iki listede de aramak fail-safe
    all_names = (
        [c.name for c in r.opponent_concepts]
        + [c.name for c in r.our_concepts]
    )
    assert "tactical_foul" in all_names
