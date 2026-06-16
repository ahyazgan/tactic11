"""In-Match Decision Assistant testleri."""
from __future__ import annotations

from app.engine.in_match_decision import MatchState, compute_in_match_decisions


def test_fresh_state_no_decisions():
    state = MatchState(minute=30, our_score=0, opp_score=0, fatigue_avg=0.4)
    r = compute_in_match_decisions(state).value
    assert r.score_state == "level"
    assert len(r.decisions) == 0
    assert "durumu koru" in r.headline.lower() or "akışı izle" in r.headline.lower()


def test_fatigue_sub_urgent_when_very_tired():
    state = MatchState(minute=70, fatigue_avg=0.85, subs_left=3)
    r = compute_in_match_decisions(state).value
    subs = [d for d in r.decisions if d.type == "sub"]
    assert subs
    assert subs[0].priority == "urgent"


def test_no_sub_when_no_subs_left():
    state = MatchState(minute=70, fatigue_avg=0.85, subs_left=0)
    r = compute_in_match_decisions(state).value
    subs = [d for d in r.decisions if d.type == "sub"]
    assert not subs


def test_intensity_up_when_trailing_late():
    state = MatchState(
        minute=80, our_score=0, opp_score=1, our_xg_running=0.5, opp_xg_running=0.7,
    )
    r = compute_in_match_decisions(state).value
    ups = [d for d in r.decisions if d.type == "intensity_up"]
    assert ups
    assert ups[0].priority == "urgent"


def test_intensity_down_when_leading_late():
    state = MatchState(minute=82, our_score=2, opp_score=1)
    r = compute_in_match_decisions(state).value
    downs = [d for d in r.decisions if d.type == "intensity_down"]
    assert downs
    assert "vakit" in downs[0].rationale.lower() or "vakit" in downs[0].recommended_action.lower()


def test_formation_change_when_drift_alert():
    state = MatchState(minute=65, formation_drift_alert=True)
    r = compute_in_match_decisions(state).value
    fcs = [d for d in r.decisions if d.type == "formation_change"]
    assert fcs
    assert "drift" in fcs[0].rationale.lower() or "şekli" in fcs[0].rationale.lower()


def test_foul_trouble_when_yellows_high():
    state = MatchState(minute=60, yellows_in_starting_xi=3, subs_left=3)
    r = compute_in_match_decisions(state).value
    ft = [d for d in r.decisions if d.type == "foul_trouble"]
    assert ft
    assert "sarı" in ft[0].rationale.lower()


def test_kill_the_game_when_leading_late():
    state = MatchState(minute=85, our_score=2, opp_score=1)
    r = compute_in_match_decisions(state).value
    ktgs = [d for d in r.decisions if d.type == "kill_the_game"]
    assert ktgs
    assert ktgs[0].priority == "optional"


def test_exploit_opportunity_when_opp_subs_used():
    state = MatchState(minute=70, opp_subs_used=4)
    r = compute_in_match_decisions(state).value
    exps = [d for d in r.decisions if d.type == "exploit_opportunity"]
    assert exps


def test_decisions_sorted_by_priority():
    state = MatchState(
        minute=82, our_score=0, opp_score=1, fatigue_avg=0.85, subs_left=3,
        yellows_in_starting_xi=2, opp_subs_used=4,
    )
    r = compute_in_match_decisions(state).value
    assert len(r.decisions) >= 2
    # ilk decision priority en yüksek olmalı
    prio_order = ["urgent", "recommended", "optional"]
    seen = [prio_order.index(d.priority) for d in r.decisions]
    assert seen == sorted(seen)


def test_audit_complete():
    state = MatchState(minute=82, fatigue_avg=0.85, subs_left=3)
    res = compute_in_match_decisions(state)
    a = res.audit.value
    assert "minute" in a
    assert "decision_count" in a
    assert "decision_types" in a
    assert "top_priority" in a


def test_headline_priority_when_decisions_present():
    state = MatchState(minute=80, our_score=0, opp_score=1, our_xg_running=0.3)
    r = compute_in_match_decisions(state).value
    assert "URGENT" in r.headline or "RECOMMENDED" in r.headline
