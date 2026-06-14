"""Referee Tendency — hakem eğilim profili (J.1)."""
from __future__ import annotations

from app.engine.referee_tendency import compute_referee_tendency


def _m(yellows: int, reds: int = 0, fouls: int = 25, penalties: int = 0,
       yellows_home: int | None = None) -> dict:
    d = {
        "yellows_total": yellows, "reds_total": reds,
        "fouls_total": fouls, "penalties": penalties,
    }
    if yellows_home is not None:
        d["yellows_home"] = yellows_home
    return d


def test_empty_history_unknown():
    r = compute_referee_tendency([], referee_id="r-1").value
    assert r.severity == "unknown"
    assert r.matches_analyzed == 0
    assert "yetersiz" in r.tactical_advice.lower()


def test_lenient_referee_low_yellows():
    """5 maç × 3 sarı = avg 3 → 3/4.5 = 0.67 → lenient (≤0.80)."""
    rows = [_m(3) for _ in range(5)]
    r = compute_referee_tendency(rows, referee_id="r-leni").value
    assert r.severity == "lenient"
    assert r.severity_score <= 0.80
    assert "lenient" in r.tactical_advice.lower()


def test_strict_referee_high_yellows():
    """6 maç × 7 sarı = avg 7 → 7/4.5 = 1.56 → strict."""
    rows = [_m(7) for _ in range(6)]
    r = compute_referee_tendency(rows, referee_id="r-strict").value
    assert r.severity == "strict"
    assert r.severity_score >= 1.20
    assert "strict" in r.tactical_advice.lower()


def test_average_severity():
    """5 maç × 4 sarı = avg 4 → 4/4.5 = 0.89 → average."""
    rows = [_m(4) for _ in range(5)]
    r = compute_referee_tendency(rows, referee_id="r-avg").value
    assert r.severity == "average"


def test_min_matches_below_threshold_returns_unknown():
    rows = [_m(7) for _ in range(3)]  # 3 < MIN_MATCHES_FOR_TENDENCY=5
    r = compute_referee_tendency(rows, referee_id="r-few").value
    assert r.severity == "unknown"


def test_cards_per_foul_calculation():
    """5 maç, her birinde 5 sarı + 25 faul → cards/foul = 25/125 = 0.20."""
    rows = [_m(5, fouls=25) for _ in range(5)]
    r = compute_referee_tendency(rows, referee_id="r").value
    assert r.cards_per_foul_ratio == 0.2


def test_penalty_rate():
    """10 maç, 4'ünde penalty → 0.4 ortalama."""
    rows = [_m(4, penalties=1 if i < 4 else 0) for i in range(10)]
    r = compute_referee_tendency(rows, referee_id="r").value
    assert r.penalty_rate_per_match == 0.4


def test_home_bias_detection():
    """Tüm sarılar ev sahibine → 100% home bias."""
    rows = [_m(5, yellows_home=5) for _ in range(5)]
    r = compute_referee_tendency(rows, referee_id="r").value
    assert r.home_yellow_share_pct == 100.0
    assert "ev sahibine" in r.tactical_advice.lower()


def test_audit_complete():
    res = compute_referee_tendency(
        [_m(7) for _ in range(6)], referee_id="r-x", referee_name="X",
    )
    a = res.audit.value
    assert a["severity"] == "strict"
    assert "yellows_per_match" in a
    assert "tactical_advice" in a
