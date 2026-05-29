"""data_quality — event-akışı kalite skoru (saf)."""
from __future__ import annotations

from app.engine.data_quality import EventStamp, compute_data_quality


def _dense(current_minute: float) -> list[EventStamp]:
    """Her dakikada ~12 event, 4 çekirdek tip dönüşümlü → sağlıklı feed."""
    types = ("pass", "defensive_action", "shot", "carry")
    out: list[EventStamp] = []
    m = 0.0
    i = 0
    while m <= current_minute:
        for _ in range(12):
            out.append(EventStamp(minute=m, event_type=types[i % 4]))
            i += 1
        m += 1.0
    return out


def test_healthy_feed_is_ok():
    r = compute_data_quality(_dense(45.0), current_minute=45.0)
    assert r.status == "ok"
    assert r.quality_score >= 0.70
    assert r.missing_types == ()
    assert r.flags == ()


def test_no_events_is_poor():
    r = compute_data_quality([], current_minute=30.0)
    assert r.status == "poor"
    assert r.quality_score == 0.0
    assert "event yok" in r.flags[0]
    assert set(r.missing_types) == {"pass", "defensive_action", "shot", "carry"}


def test_stale_feed_flagged():
    # Son event 10. dk, şu an 30. dk → 20 dk bayat
    events = [EventStamp(minute=float(i) * 0.5, event_type="pass") for i in range(20)]
    events += [EventStamp(minute=2.0, event_type="defensive_action"),
               EventStamp(minute=3.0, event_type="shot"),
               EventStamp(minute=4.0, event_type="carry")]
    r = compute_data_quality(events, current_minute=30.0)
    assert r.freshness_min > 5.0
    assert any("bayat" in f for f in r.flags)
    assert r.quality_score < 1.0


def test_coverage_gap_flagged():
    # 0-5 yoğun, sonra 25. dk'ya kadar boşluk
    events = [EventStamp(minute=float(i) * 0.2, event_type="pass") for i in range(25)]
    events.append(EventStamp(minute=25.0, event_type="pass"))
    r = compute_data_quality(events, current_minute=25.0)
    assert r.largest_gap_min > 8.0
    assert any("kapsama" in f for f in r.flags)


def test_missing_type_penalizes():
    # Sadece pas — shot/def/carry yok
    events = [EventStamp(minute=float(i) * 0.1, event_type="pass") for i in range(200)]
    r = compute_data_quality(events, current_minute=20.0)
    assert "shot" in r.missing_types
    assert "defensive_action" in r.missing_types
    assert r.quality_score < 0.70


def test_score_feeds_confidence_range():
    """quality_score her zaman 0..1 — confidence.data_quality'ye uygun."""
    r = compute_data_quality(_dense(60.0), current_minute=60.0)
    assert 0.0 <= r.quality_score <= 1.0
