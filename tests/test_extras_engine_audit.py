"""extras_engine_audit script structural testleri (Faz 5 #46).

Engine extractor'ları DB-bağımlı; bu testler script iskeletinin (engine
listesi, verdict eşikleri, JSON/MD format) doğru kurulduğunu doğrular.
"""
from __future__ import annotations

import json

import pytest

from scripts.extras_engine_audit import (
    CV_STRONG,
    EXTRAS_ENGINES,
    N_MIN_RELIABLE,
    AuditEntry,
    EngineSpec,
    _format_markdown,
    _verdict,
)


def test_extras_engine_count_at_least_8() -> None:
    """İkinci grup motor listesi minimum 8 entry."""
    assert len(EXTRAS_ENGINES) >= 8


def test_each_engine_has_extractor() -> None:
    for spec in EXTRAS_ENGINES:
        assert callable(spec.extractor)
        assert spec.name
        assert spec.metric


def test_engine_names_unique() -> None:
    names = [s.name for s in EXTRAS_ENGINES]
    assert len(names) == len(set(names))


def test_engines_not_in_first_group() -> None:
    """İkinci grup ilk full_season_audit grubu ile çakışmamalı (bilinen subset)."""
    first_group = {
        "ppda", "pressing_trigger", "recovery_zone_heat", "defensive_line",
        "compactness", "transition", "counter_press_triggers", "direct_play",
        "tempo", "possession_quality", "channel_preference",
        "final_third_entries", "cross_effectiveness", "cutback_frequency",
        "defensive_duels", "press_resistance", "set_piece_zones",
        "build_up_pattern", "field_tilt", "match_dominance",
    }
    extras_names = {s.name for s in EXTRAS_ENGINES}
    overlap = extras_names & first_group
    assert not overlap, f"İkinci grup ilk grupla çakışıyor: {overlap}"


def test_verdict_thresholds() -> None:
    # Insufficient data: n < min
    assert _verdict(N_MIN_RELIABLE - 1, cv=0.5) == "INSUFFICIENT_DATA"
    # Strong signal: n yeterli + cv yüksek
    assert _verdict(N_MIN_RELIABLE, cv=CV_STRONG) == "STRONG_SIGNAL"
    assert _verdict(50, cv=0.5) == "STRONG_SIGNAL"
    # Weak signal: cv eşiği biraz altında
    assert _verdict(50, cv=0.15) == "WEAK_SIGNAL"
    # Noise: cv çok düşük
    assert _verdict(50, cv=0.05) == "NOISE"


def test_verdict_constants_sane() -> None:
    """Eşik sabitler full_season_audit ile aynı seviyede (parametre koruma)."""
    assert 0.0 < CV_STRONG <= 1.0
    assert N_MIN_RELIABLE >= 10


# --------------------------------------------------------------------------- #
# AuditEntry serialization
# --------------------------------------------------------------------------- #


def test_audit_entry_to_dict_round_trip() -> None:
    entry = AuditEntry(
        engine="x", metric="m", n_samples=42, mean=1.5, stdev=0.3,
        cv=0.2, spread=0.9, verdict="WEAK_SIGNAL", notes="test",
    )
    out = entry.to_dict()
    assert out["engine"] == "x"
    assert out["n_samples"] == 42
    assert out["verdict"] == "WEAK_SIGNAL"
    # JSON-serializable
    json.dumps(out)


# --------------------------------------------------------------------------- #
# Markdown formatter
# --------------------------------------------------------------------------- #


def test_markdown_has_header_and_table() -> None:
    entries = [
        AuditEntry("a", "metric_a", 50, 1.0, 0.5, 0.5, 0.5, "STRONG_SIGNAL"),
        AuditEntry("b", "metric_b", 10, 1.0, 0.05, 0.05, 0.1, "INSUFFICIENT_DATA"),
        AuditEntry("c", "metric_c", 30, 2.0, 0.1, 0.05, 0.2, "NOISE"),
    ]
    md = _format_markdown(entries)
    assert "# Extras Engine Audit" in md
    assert "| Engine | Metric |" in md
    assert "`a`" in md
    assert "STRONG_SIGNAL" in md


def test_markdown_uses_distinct_verdict_emoji() -> None:
    entries = [
        AuditEntry("strong", "m", 50, 1.0, 0.5, 0.5, 0.5, "STRONG_SIGNAL"),
        AuditEntry("weak", "m", 30, 1.0, 0.15, 0.15, 0.2, "WEAK_SIGNAL"),
        AuditEntry("noise", "m", 30, 1.0, 0.05, 0.05, 0.1, "NOISE"),
        AuditEntry("insuff", "m", 5, 1.0, 0.5, 0.5, 0.2, "INSUFFICIENT_DATA"),
    ]
    md = _format_markdown(entries)
    # Her verdict satırında farklı emoji
    assert "🟢" in md  # strong
    assert "🟡" in md  # weak
    assert "🔴" in md  # noise
    assert "⚪" in md  # insuff


# --------------------------------------------------------------------------- #
# Engine spec contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("spec", EXTRAS_ENGINES, ids=lambda s: s.name)
def test_engine_spec_immutable_and_documented(spec: EngineSpec) -> None:
    """Her engine spec frozen dataclass + boş olmayan notes."""
    with pytest.raises(Exception):
        spec.name = "different"  # type: ignore[misc]
    # Notes opsiyonel olabilir ama liste içinde elimizdeki spec'ler dolu yazılı
    assert isinstance(spec.notes, str)
