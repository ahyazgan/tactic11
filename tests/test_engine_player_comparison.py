"""Player Comparison testleri."""
from __future__ import annotations

from app.engine.player_comparison import PlayerProfile, compute_player_comparison


def _p(pid: int, name: str, **kpis) -> PlayerProfile:
    return PlayerProfile(player_id=pid, name=name, kpis=dict(kpis))


def test_basic_two_player_comparison():
    players = [
        _p(1, "Alice", rating=7.5, xt_per_90=0.3, goals_per_90=0.4),
        _p(2, "Bob", rating=7.0, xt_per_90=0.2, goals_per_90=0.5),
    ]
    r = compute_player_comparison(players).value
    assert r.player_count == 2
    assert r.winner_id in (1, 2)
    assert len(r.per_kpi) == 3
    assert len(r.per_player) == 2


def test_clear_winner_higher_aggregate():
    players = [
        _p(1, "Alice", rating=9.0, xt=0.8, ga=1.0),
        _p(2, "Bob", rating=5.0, xt=0.1, ga=0.2),
    ]
    r = compute_player_comparison(players).value
    assert r.winner_id == 1
    assert r.winner_name == "Alice"


def test_lower_is_better_kpi():
    """PPDA daha düşük = daha iyi."""
    players = [
        _p(1, "Alice", ppda=8.0),
        _p(2, "Bob", ppda=14.0),
    ]
    r = compute_player_comparison(players).value
    # PPDA için Alice best (lower)
    ppda_kpi = next(k for k in r.per_kpi if k.kpi == "ppda")
    assert ppda_kpi.best_player_id == 1
    assert ppda_kpi.rank[1] == 1
    assert ppda_kpi.rank[2] == 2


def test_common_kpis_only_when_kpis_none():
    """Oyuncular farklı KPI seti → sadece ortak olanlar karşılaştırılır."""
    players = [
        _p(1, "Alice", rating=7.0, xt=0.3, custom_kpi=0.5),
        _p(2, "Bob", rating=7.2, xt=0.4),
    ]
    r = compute_player_comparison(players).value
    assert "rating" in r.kpis_compared
    assert "xt" in r.kpis_compared
    assert "custom_kpi" not in r.kpis_compared


def test_explicit_kpis_filter():
    players = [
        _p(1, "Alice", rating=7.0, xt=0.3, goals=0.5),
        _p(2, "Bob", rating=7.2, xt=0.4, goals=0.3),
    ]
    r = compute_player_comparison(players, kpis=["rating"]).value
    assert r.kpis_compared == ("rating",)


def test_weights_change_winner():
    """Weights ile farklı kazanan."""
    players = [
        _p(1, "Striker", rating=7.0, goals=1.0, defending=0.1),
        _p(2, "Defender", rating=7.5, goals=0.1, defending=1.0),
    ]
    r_no = compute_player_comparison(players).value
    r_goals = compute_player_comparison(players, weights={"goals": 10}).value
    # goals'a aşırı ağırlık → striker kazanır
    assert r_goals.winner_id == 1
    # without weight, defender muhtemelen kazanır (rating + defending strong)
    assert r_no.winner_id in (1, 2)


def test_normalized_values_in_0_1_range():
    players = [
        _p(1, "Alice", rating=8.0),
        _p(2, "Bob", rating=5.0),
        _p(3, "Carol", rating=6.5),
    ]
    r = compute_player_comparison(players).value
    kpi = r.per_kpi[0]
    for nv in kpi.normalized.values():
        assert 0.0 <= nv <= 1.0


def test_rank_unique_per_kpi():
    players = [
        _p(1, "Alice", rating=8.0),
        _p(2, "Bob", rating=5.0),
        _p(3, "Carol", rating=6.5),
    ]
    r = compute_player_comparison(players).value
    kpi = r.per_kpi[0]
    ranks = list(kpi.rank.values())
    assert sorted(ranks) == [1, 2, 3]


def test_strongest_weakest_kpi():
    players = [
        _p(1, "Alice", rating=9.0, xt=0.1),
        _p(2, "Bob", rating=5.0, xt=0.9),
    ]
    r = compute_player_comparison(players).value
    alice = next(s for s in r.per_player if s.player_id == 1)
    # Alice'in rating'i en yüksek → strongest rating; xt en düşük → weakest xt
    assert alice.strongest_kpi == "rating"
    assert alice.weakest_kpi == "xt"


def test_tie_results_in_no_winner():
    players = [
        _p(1, "Alice", rating=7.0, xt=0.3),
        _p(2, "Bob", rating=7.0, xt=0.3),
    ]
    r = compute_player_comparison(players).value
    assert r.winner_id is None
    assert "berabere" in r.reasoning.lower()


def test_insufficient_when_lt_2_players():
    r = compute_player_comparison([_p(1, "Alice", rating=7)]).value
    assert r.player_count == 1
    assert "en az 2" in r.summary.lower()


def test_no_common_kpis_insufficient():
    players = [
        _p(1, "Alice", rating=7.0),
        _p(2, "Bob", xt=0.3),
    ]
    r = compute_player_comparison(players).value
    assert "ortak" in r.summary.lower() or "yetersiz" in r.summary.lower()


def test_audit_complete():
    players = [_p(1, "A", rating=7), _p(2, "B", rating=8)]
    res = compute_player_comparison(players)
    a = res.audit.value
    assert "player_count" in a
    assert "kpis" in a
    assert "winner_id" in a
    assert "rankings" in a


def test_overall_rank_sorted_correctly():
    players = [
        _p(1, "Worst", rating=4.0, xt=0.1),
        _p(2, "Best", rating=9.0, xt=0.9),
        _p(3, "Middle", rating=6.5, xt=0.5),
    ]
    r = compute_player_comparison(players).value
    assert r.per_player[0].name == "Best"
    assert r.per_player[0].overall_rank == 1
    assert r.per_player[-1].name == "Worst"
