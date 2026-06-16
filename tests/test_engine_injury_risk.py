"""engine.injury_risk + squad_depth + rotation_plan tests."""
from __future__ import annotations

from app.engine.injury_risk import compute_injury_risk
from app.engine.rotation_plan import compute_rotation_plan
from app.engine.squad_depth import compute_squad_depth

# --------------------------------------------------------------------------- #
# injury_risk
# --------------------------------------------------------------------------- #


def test_high_load_high_age_severe():
    r = compute_injury_risk(
        100, minutes_per_week=400, back_to_back_count=4, age=34,
    ).value
    assert r.risk_level in ("high", "severe")
    assert r.risk_score >= 50


def test_low_load_young_low_risk():
    r = compute_injury_risk(
        100, minutes_per_week=150, back_to_back_count=0, age=22,
    ).value
    assert r.risk_level == "low"


def test_acwr_danger_zone_maxes_load():
    """ACWR >= 1.5 → load_factor 40."""
    r = compute_injury_risk(
        100, minutes_per_week=200, back_to_back_count=1, age=25,
        acute_minutes_7d=400, chronic_minutes_28d_avg=200,
    ).value
    assert r.acwr == 2.0
    assert r.acwr_flag == "danger"
    assert r.load_factor == 40.0


def test_acwr_undertrained_flag():
    r = compute_injury_risk(
        100, minutes_per_week=100, back_to_back_count=0, age=25,
        acute_minutes_7d=50, chronic_minutes_28d_avg=200,
    ).value
    assert r.acwr_flag == "undertrained"


def test_factors_sum_to_score():
    r = compute_injury_risk(
        100, minutes_per_week=300, back_to_back_count=2, age=30,
    ).value
    expected = min(100.0, r.load_factor + r.age_factor + r.frequency_factor)
    assert abs(r.risk_score - expected) < 0.2


def test_audit_includes_factors():
    r = compute_injury_risk(100, minutes_per_week=200, back_to_back_count=1)
    assert "load_factor" in r.audit.value
    assert "age_factor" in r.audit.value


# --------------------------------------------------------------------------- #
# squad_depth
# --------------------------------------------------------------------------- #


def test_insufficient_position():
    """1 kaleci (min 2) → insufficient."""
    squad = [{"player_id": 1, "position": "G", "age": 28}]
    r = compute_squad_depth(11, squad).value
    gk = next(p for p in r.by_position if p.position == "G")
    assert gk.depth_status == "insufficient"


def test_aging_position_flagged():
    """3 defans, hepsi 33+ → aging risk."""
    squad = [
        {"player_id": i, "position": "D", "age": 34}
        for i in range(1, 4)
    ]
    r = compute_squad_depth(11, squad).value
    d = next(p for p in r.by_position if p.position == "D")
    assert d.aging_risk is True
    assert "D" in r.aging_positions


def test_surplus_position():
    """10 orta saha (min 5) → surplus."""
    squad = [
        {"player_id": i, "position": "M", "age": 25}
        for i in range(1, 11)
    ]
    r = compute_squad_depth(11, squad).value
    m = next(p for p in r.by_position if p.position == "M")
    assert m.depth_status == "surplus"


def test_weakest_position_identified():
    """G/D/M dolu, sadece F eksik → weakest=F (en büyük göreli açık)."""
    squad = (
        [{"player_id": i, "position": "G", "age": 25} for i in range(1, 3)]
        + [{"player_id": i, "position": "D", "age": 25} for i in range(3, 9)]
        + [{"player_id": i, "position": "M", "age": 25} for i in range(9, 14)]
        + [{"player_id": 14, "position": "F", "age": 25}]  # 1/4 → açık -3
    )
    r = compute_squad_depth(11, squad).value
    assert r.weakest_position == "F"


def test_avg_age_calculated():
    squad = [
        {"player_id": 1, "position": "M", "age": 20},
        {"player_id": 2, "position": "M", "age": 30},
    ]
    r = compute_squad_depth(11, squad).value
    m = next(p for p in r.by_position if p.position == "M")
    assert m.avg_age == 25.0


# --------------------------------------------------------------------------- #
# rotation_plan
# --------------------------------------------------------------------------- #


def test_high_risk_players_become_candidates():
    loads = [
        {"player_external_id": 1, "risk_level": "extreme",
         "minutes_per_week": 400, "back_to_back_count": 4},
        {"player_external_id": 2, "risk_level": "low",
         "minutes_per_week": 100, "back_to_back_count": 0},
    ]
    r = compute_rotation_plan(
        11, loads, upcoming_matches=3, dense_schedule=True,
    ).value
    assert r.rotate_count == 1
    assert r.candidates[0].player_external_id == 1


def test_rotation_intensity_aggressive():
    loads = [
        {"player_external_id": i, "risk_level": "extreme",
         "minutes_per_week": 400, "back_to_back_count": 3}
        for i in range(1, 5)
    ]
    r = compute_rotation_plan(
        11, loads, upcoming_matches=4, dense_schedule=True,
    ).value
    assert r.rotation_intensity == "aggressive"


def test_rotation_minimal_no_risk():
    loads = [
        {"player_external_id": 1, "risk_level": "low",
         "minutes_per_week": 100, "back_to_back_count": 0},
    ]
    r = compute_rotation_plan(11, loads).value
    assert r.rotate_count == 0
    assert r.rotation_intensity == "minimal"


def test_rest_priority_sorted():
    """Extreme oyuncu low'dan önce, priority 1."""
    loads = [
        {"player_external_id": 1, "risk_level": "high",
         "minutes_per_week": 280, "back_to_back_count": 0},
        {"player_external_id": 2, "risk_level": "extreme",
         "minutes_per_week": 400, "back_to_back_count": 3},
    ]
    r = compute_rotation_plan(11, loads).value
    assert r.candidates[0].player_external_id == 2
    assert r.candidates[0].rest_priority == 1
