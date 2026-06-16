"""Threat Pathway engine testleri."""
from __future__ import annotations

from app.engine.threat_pathway import PathwayEvent, compute_threat_pathway


def test_left_wing_dominant_when_all_events_left():
    events = [
        PathwayEvent(start_y=40, end_y=10, threat_weight=0.2),
        PathwayEvent(start_y=30, end_y=15, threat_weight=0.3, is_shot=True),
        PathwayEvent(start_y=20, end_y=12, threat_weight=0.4, is_assist=True),
    ]
    r = compute_threat_pathway(events).value
    assert r.top_lane == "left_wing"
    assert r.top_lane_share > 0.6
    assert "Sol kanat" in r.summary
    assert "Sol kanat" in r.our_exploit_advice or "LB" in r.our_exploit_advice


def test_central_threat_picks_central_lane():
    events = [
        PathwayEvent(start_y=40, end_y=40, threat_weight=0.3, is_shot=True),
        PathwayEvent(start_y=38, end_y=42, threat_weight=0.25),
    ]
    r = compute_threat_pathway(events).value
    assert r.top_lane == "central"


def test_empty_events_no_top_lane():
    r = compute_threat_pathway([]).value
    assert r.top_lane is None
    assert r.total_events == 0
    assert any("Event yok" in n for n in r.notes)


def test_half_space_classification():
    # y=30 → left_half_space; y=50 → right_half_space
    events = [
        PathwayEvent(start_y=40, end_y=30, threat_weight=0.5),
        PathwayEvent(start_y=40, end_y=50, threat_weight=0.4),
    ]
    r = compute_threat_pathway(events).value
    lanes = {ls.lane for ls in r.lanes if ls.event_count > 0}
    assert "left_half_space" in lanes
    assert "right_half_space" in lanes


def test_zero_threat_weight_falls_to_volume_only():
    events = [
        PathwayEvent(start_y=40, end_y=70, threat_weight=0.0),
        PathwayEvent(start_y=40, end_y=72, threat_weight=0.0),
    ]
    r = compute_threat_pathway(events).value
    # threat=0 → no top lane (share computation skipped)
    assert r.top_lane is None
    assert any("threat ağırlığı sıfır" in n.lower() for n in r.notes)


def test_counter_advice_for_left_wing():
    events = [PathwayEvent(start_y=40, end_y=10, threat_weight=1.0)]
    r = compute_threat_pathway(events, perspective="opponent").value
    assert r.top_lane == "left_wing"
    assert "RB" in r.counter_advice or "winger" in r.counter_advice.lower() or "sağ" in r.counter_advice.lower()


def test_shot_count_per_lane():
    events = [
        PathwayEvent(start_y=40, end_y=10, threat_weight=0.3, is_shot=True),
        PathwayEvent(start_y=40, end_y=12, threat_weight=0.2, is_shot=True),
        PathwayEvent(start_y=40, end_y=70, threat_weight=0.1),
    ]
    r = compute_threat_pathway(events).value
    lw = next(ls for ls in r.lanes if ls.lane == "left_wing")
    assert lw.shots_in_lane == 2


def test_lanes_sorted_by_threat_desc():
    events = [
        PathwayEvent(start_y=40, end_y=10, threat_weight=0.5),
        PathwayEvent(start_y=40, end_y=70, threat_weight=0.3),
        PathwayEvent(start_y=40, end_y=40, threat_weight=0.1),
    ]
    r = compute_threat_pathway(events).value
    threats = [ls.threat_total for ls in r.lanes]
    assert threats == sorted(threats, reverse=True)


def test_audit_complete():
    events = [PathwayEvent(start_y=40, end_y=10, threat_weight=0.5)]
    res = compute_threat_pathway(events)
    a = res.audit.value
    assert "total_events" in a
    assert "top_lane" in a
    assert "lane_threats" in a
    assert a["top_lane"] == "left_wing"


def test_boundary_y_classifications():
    # y=22 → left_half_space (boundary), y=44 → right_half_space, y=58 → right_wing
    events = [
        PathwayEvent(start_y=40, end_y=22, threat_weight=0.1),
        PathwayEvent(start_y=40, end_y=44, threat_weight=0.1),
        PathwayEvent(start_y=40, end_y=58, threat_weight=0.1),
    ]
    r = compute_threat_pathway(events).value
    lanes_with_events = {ls.lane for ls in r.lanes if ls.event_count > 0}
    # Sınırlar dahil olduğu lane'e dahil
    assert "left_half_space" in lanes_with_events
    assert "right_half_space" in lanes_with_events
    assert "right_wing" in lanes_with_events
