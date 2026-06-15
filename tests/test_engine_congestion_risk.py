"""Congestion Risk — fikstür yoğunluğu skor + tavsiye."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.engine.congestion_risk import FixtureItem, compute_congestion_risk

_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _f(days_ahead: float, comp: str = "league",
       travel: float = 100.0, home: bool = True) -> FixtureItem:
    return FixtureItem(
        kickoff=_NOW + timedelta(days=days_ahead),
        is_home=home, competition=comp, travel_km=travel,
    )


def test_empty_fixtures_returns_low():
    r = compute_congestion_risk([], now=_NOW).value
    assert r.fixtures_count == 0
    assert r.phase == "low"
    assert "yok" in r.advice


def test_normal_weekly_fixtures_low_score():
    """Sadece haftada 1 lig maçı, 28 gün → low congestion."""
    fixtures = [_f(7), _f(14), _f(21), _f(28)]
    r = compute_congestion_risk(fixtures, now=_NOW).value
    assert r.phase == "low"
    assert r.critical_rest_count == 0
    assert r.competitions == ("league",)


def test_critical_short_rest_3_days():
    """3 maç 2-3 gün arası → kritik dinlenme sayımı yüksek."""
    fixtures = [_f(1), _f(3.5), _f(6.5)]  # 60sa + 72sa gaps
    r = compute_congestion_risk(fixtures, now=_NOW).value
    # 2 gap; her ikisi de ≤72sa → critical_g=2 → rest_term ≥50
    assert r.critical_rest_count >= 1
    assert r.phase in ("moderate", "high", "critical")
    assert r.congestion_score >= 30


def test_multi_competition_penalty():
    """Lig + kupa + Avrupa → comp_term ≥30."""
    fixtures = [
        _f(2, "league"), _f(5, "cup"),
        _f(8, "champions"), _f(12, "league"),
    ]
    r = compute_congestion_risk(fixtures, now=_NOW).value
    assert len(r.competitions) == 3
    # extra_comps = 2 → comp_term = 30
    assert r.congestion_score >= 30


def test_high_travel_penalty():
    """Yüksek seyahat (700km/maç) → travel_term"""
    fixtures = [_f(7, travel=700), _f(14, travel=900)]
    r = compute_congestion_risk(fixtures, now=_NOW).value
    assert r.avg_travel_km_per_match >= 500
    assert "seyahat" in " ".join(r.risk_areas)


def test_critical_phase_combines_all():
    """Kısa rest + maraton + multi-comp → kritik faz."""
    fixtures = [
        _f(1, "league", travel=600),
        _f(3.5, "cup", travel=800),    # 60sa rest
        _f(5.5, "champions", travel=700),  # 48sa rest
        _f(8, "league", travel=600),    # 60sa rest
        _f(11, "cup", travel=500),
    ]
    r = compute_congestion_risk(fixtures, now=_NOW).value
    assert r.phase == "critical"
    assert "rotasyon" in r.advice.lower() or "rota" in r.advice.lower()


def test_fixtures_outside_window_excluded():
    """50 gün sonraki maç default 28gün penceresinde değil."""
    fixtures = [_f(7), _f(50)]
    r = compute_congestion_risk(fixtures, now=_NOW).value
    assert r.fixtures_count == 1


def test_audit_complete():
    res = compute_congestion_risk([_f(7), _f(10)], now=_NOW)
    a = res.audit.value
    assert "congestion_score" in a
    assert "phase" in a
    assert "advice" in a
