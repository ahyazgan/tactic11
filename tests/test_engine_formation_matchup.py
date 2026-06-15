"""Formation Matchup — (our × opp) 8-vektör + advice."""
from __future__ import annotations

from app.engine.formation_matchup import (
    compute_formation_matchup,
    list_formations,
)


def test_list_formations_has_8():
    forms = list_formations()
    assert len(forms) >= 8
    ids = {f.id for f in forms}
    assert "4-3-3" in ids
    assert "4-2-3-1" in ids
    assert "5-3-2" in ids


def test_specific_matchup_4_3_3_vs_4_2_3_1():
    r = compute_formation_matchup("4-3-3", "4-2-3-1").value
    assert r.expectation.raw[4] >= 0.55  # width_clash
    assert len(r.advice) >= 2
    assert any("kanat" in a.lower() or "winger" in a.lower()
               for a in r.advice)


def test_4_3_3_vs_5_3_2_low_block_warning():
    """5-3-2 düşük block → space_behind_lines düşük + advice'da 'switch/half-space/uzaktan şut'."""
    r = compute_formation_matchup("4-3-3", "5-3-2").value
    assert r.expectation.values["space_behind_lines"] <= 0.35
    texts = " ".join(r.advice).lower()
    assert "switch" in texts or "uzaktan şut" in texts or "half-space" in texts


def test_5_3_2_vs_4_3_3_defensive_stable():
    """5-3-2 hücum az ama defansif sağlam (our_xt low + transition_speed)."""
    r = compute_formation_matchup("5-3-2", "4-3-3").value
    assert r.expectation.values["our_xt_expected"] <= 0.40
    assert r.expectation.values["transition_speed"] >= 0.40


def test_mirror_matchup_neutral():
    """Aynı formasyon → 0.50 civarı dengeli vektör."""
    r = compute_formation_matchup("4-3-3", "4-3-3").value
    for label in ("our_xt_expected", "opp_xt_expected",
                  "our_ppda_advantage", "midfield_control"):
        assert 0.40 <= r.expectation.values[label] <= 0.60


def test_inverted_fallback():
    """KB'de (3-5-2, 4-2-3-1) yok ama (4-2-3-1, 3-5-2) var → ters çevirme."""
    r = compute_formation_matchup("3-5-2", "4-2-3-1").value
    if r.notes:
        # ya inverted bulundu, ya nötr fallback
        assert any("ters" in n or "tanımlı değil" in n for n in r.notes)


def test_unknown_formation_neutral_advice():
    """Tamamen tanımsız formasyon → nötr 0.5 + generic advice."""
    r = compute_formation_matchup("0-0-0", "x-y-z").value
    assert all(0.49 <= v <= 0.51 for v in r.expectation.raw)
    assert len(r.notes) >= 1


def test_audit_complete():
    res = compute_formation_matchup("4-3-3", "5-3-2")
    a = res.audit.value
    assert "expectation" in a
    assert "advice_count" in a
    assert "summary" in a
    assert "inverted" in a
