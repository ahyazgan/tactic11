"""Role Matcher — oyuncu rol arketip eşleme testleri."""
from __future__ import annotations

from app.engine.role_matcher import (
    PlayerStatVector,
    compute_role_match,
    list_roles,
)


def _stats(**kwargs) -> PlayerStatVector:
    base = dict(
        defensive_actions_pct=0.5, tackle_pct=0.5, interception_pct=0.5,
        pass_completion_pct=0.7, progressive_pass_pct=0.5, key_pass_pct=0.3,
        dribble_pct=0.3, shot_per_90_pct=0.2,
    )
    base.update(kwargs)
    return PlayerStatVector(**base)


def test_kb_has_min_25_roles():
    roles = list_roles()
    assert len(roles) >= 25
    # Pozisyon grupları
    groups = {r.get("position_group") for r in roles}
    assert {"GK", "CB", "FB", "DM", "CM", "AM", "W", "FW"}.issubset(groups)


def test_poacher_high_shot_per_90():
    """Yüksek shot_per_90 + düşük dribble + low aerial → poacher (vs target_man)."""
    s = _stats(shot_per_90_pct=0.80, pass_completion_pct=0.70,
               defensive_actions_pct=0.30, tackle_pct=0.25,
               interception_pct=0.20, dribble_pct=0.25,
               progressive_pass_pct=0.30, key_pass_pct=0.35)
    r = compute_role_match(7, s, position_group="FW").value
    assert r.top_match is not None
    # poacher veya complete_forward yakın aralık
    assert r.top_match.name in ("poacher", "complete_forward")


def test_regista_deep_pass_range():
    """Yüksek pass + progressive_pass + low dribble → regista or deep_lying."""
    s = _stats(pass_completion_pct=0.93, progressive_pass_pct=0.80,
               defensive_actions_pct=0.65, dribble_pct=0.10,
               shot_per_90_pct=0.10, key_pass_pct=0.45)
    r = compute_role_match(8, s, position_group="DM").value
    assert r.top_match is not None
    assert r.top_match.name in ("regista", "deep_lying_playmaker")


def test_inside_forward_winger():
    """Yüksek dribble + key_pass + medium shot → inside_forward."""
    s = _stats(dribble_pct=0.80, key_pass_pct=0.65, shot_per_90_pct=0.50,
               pass_completion_pct=0.75, defensive_actions_pct=0.45,
               progressive_pass_pct=0.60)
    r = compute_role_match(11, s, position_group="W").value
    assert r.top_match is not None
    assert r.top_match.name in ("inside_forward", "inverted_winger")


def test_traditional_cb_high_defensive():
    """Yüksek def_actions + tackle + interception → traditional_cb / aggressive."""
    s = _stats(defensive_actions_pct=0.92, tackle_pct=0.82, interception_pct=0.72,
               pass_completion_pct=0.78, progressive_pass_pct=0.30,
               key_pass_pct=0.10, dribble_pct=0.05, shot_per_90_pct=0.10)
    r = compute_role_match(4, s, position_group="CB").value
    assert r.top_match is not None
    assert r.top_match.name in ("traditional_cb", "aggressive_cb")


def test_false_nine_link_play():
    """Yüksek pass + key_pass + medium dribble → false_nine."""
    s = _stats(pass_completion_pct=0.88, key_pass_pct=0.85,
               dribble_pct=0.55, shot_per_90_pct=0.45,
               defensive_actions_pct=0.30, progressive_pass_pct=0.65)
    r = compute_role_match(9, s, position_group="FW").value
    assert r.top_match is not None
    assert r.top_match.name in ("false_nine", "second_striker")


def test_position_filter_restricts():
    """GK filter → sadece kaleci rolleri arası eşleşir."""
    s = _stats(pass_completion_pct=0.85, defensive_actions_pct=0.55)
    r = compute_role_match(1, s, position_group="GK").value
    assert r.top_match is not None
    assert r.top_match.position_group == "GK"


def test_no_filter_searches_all():
    s = _stats()
    r = compute_role_match(1, s).value
    assert r.position_group_filter is None
    assert r.top_match is not None


def test_secondary_matches_count():
    s = _stats(pass_completion_pct=0.90, progressive_pass_pct=0.75)
    r = compute_role_match(8, s, top_n_secondary=3).value
    assert len(r.secondary_matches) == 3


def test_audit_complete():
    s = _stats(shot_per_90_pct=0.8)
    res = compute_role_match(9, s, position_group="FW")
    a = res.audit.value
    assert "top_role" in a
    assert "top_similarity" in a
    assert "secondary_roles" in a
    assert "summary" in a
