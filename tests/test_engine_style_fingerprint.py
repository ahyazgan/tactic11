"""Opponent Style Fingerprint — 8-vektör cosine arketip eşleme."""
from __future__ import annotations

from app.engine.style_fingerprint import (
    TeamMatchStat,
    compute_style_fingerprint,
    list_archetypes,
)


def _stat(**overrides) -> TeamMatchStat:
    base = dict(
        ppda=12.0, field_tilt_pct=50.0, direct_play_pct=22.0,
        counter_threat=0.35, set_piece_share_pct=20.0, width_pct=55.0,
        high_line_risk=0.4, press_height=0.5,
    )
    base.update(overrides)
    return TeamMatchStat(**base)


def test_archetypes_library_has_8():
    archs = list_archetypes()
    assert len(archs) >= 8
    names = {a.name for a in archs}
    assert "klopp_press" in names
    assert "pep_possession" in names
    assert "atletico_compact" in names


def test_empty_stats_returns_insufficient():
    r = compute_style_fingerprint([]).value
    assert r.sample_size == 0
    assert r.confidence == "insufficient"


def test_klopp_press_match_high_pressing_counter():
    """Düşük PPDA + yüksek press_height + counter threat → klopp_press top."""
    stats = [
        _stat(ppda=7.0, press_height=0.85, counter_threat=0.8,
              field_tilt_pct=55, high_line_risk=0.75) for _ in range(5)
    ]
    r = compute_style_fingerprint(stats).value
    assert r.top_archetype.name == "klopp_press"
    assert r.confidence in ("medium", "high")
    assert "Pres" in r.summary or "pres" in r.summary


def test_pep_possession_match():
    """Yüksek field_tilt + düşük direct_play → pep_possession."""
    stats = [
        _stat(ppda=11.0, field_tilt_pct=85, direct_play_pct=10,
              press_height=0.55) for _ in range(5)
    ]
    r = compute_style_fingerprint(stats).value
    assert r.top_archetype.name == "pep_possession"


def test_atletico_compact_match():
    """Düşük field_tilt + yüksek set_piece + düşük press_height."""
    stats = [
        _stat(ppda=14, field_tilt_pct=40, direct_play_pct=35,
              counter_threat=0.5, set_piece_share_pct=55,
              press_height=0.30, high_line_risk=0.20, width_pct=30)
        for _ in range(5)
    ]
    r = compute_style_fingerprint(stats).value
    assert r.top_archetype.name == "atletico_compact"


def test_lecce_direct_long_ball():
    """Yüksek direct_play + düşük possession → lecce_direct."""
    stats = [
        _stat(ppda=18, field_tilt_pct=30, direct_play_pct=85,
              counter_threat=0.55, set_piece_share_pct=40,
              press_height=0.40)
        for _ in range(5)
    ]
    r = compute_style_fingerprint(stats).value
    assert r.top_archetype.name == "lecce_direct"


def test_counter_play_advice_present_for_klopp():
    """klopp_press eşleşmesinde counter playbook satırları döner."""
    stats = [
        _stat(ppda=7.0, press_height=0.85, counter_threat=0.8,
              field_tilt_pct=55, high_line_risk=0.75) for _ in range(5)
    ]
    r = compute_style_fingerprint(stats).value
    advices = r.counter_play_advice
    assert len(advices) >= 2
    assert any("üçüncü" in a.lower() or "kombinasyon" in a.lower() for a in advices)


def test_few_samples_low_confidence():
    """1-2 maç sample → insufficient confidence."""
    stats = [_stat(ppda=7.0, press_height=0.85) for _ in range(2)]
    r = compute_style_fingerprint(stats).value
    assert r.confidence == "insufficient"


def test_second_archetype_returned():
    """5 maç → top + second arketip ikisi de dolar."""
    stats = [_stat(ppda=10.0) for _ in range(5)]
    r = compute_style_fingerprint(stats).value
    assert r.second_archetype is not None
    assert r.second_similarity > 0


def test_average_vector_8_dim():
    stats = [_stat() for _ in range(3)]
    r = compute_style_fingerprint(stats).value
    assert len(r.avg_vector.to_tuple()) == 8
    # Tüm değerler 0..1 arası
    for v in r.avg_vector.to_tuple():
        assert 0.0 <= v <= 1.0


def test_audit_complete():
    stats = [_stat() for _ in range(3)]
    res = compute_style_fingerprint(stats)
    a = res.audit.value
    assert "top_archetype" in a
    assert "top_similarity" in a
    assert "summary" in a
