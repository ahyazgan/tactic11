"""Team Form Health engine testleri."""
from __future__ import annotations

from app.engine.team_form_health import PlayerSeries, compute_team_form_health


def _series(pid, name, ratings, pos=""):
    return PlayerSeries(
        player_id=pid, name=name, ratings=tuple(ratings), position_group=pos,
    )


def test_all_improving_team_health_high():
    players = [
        _series(1, "A", [6.0, 6.5, 7.0, 7.5, 8.0]),
        _series(2, "B", [5.5, 6.0, 6.5, 7.0, 7.5]),
        _series(3, "C", [7.0, 7.2, 7.4, 7.6, 7.8]),
    ]
    r = compute_team_form_health(players).value
    assert r.pct_improving > 50
    assert r.team_health_score > 0


def test_all_declining_team_health_low():
    players = [
        _series(1, "A", [8.0, 7.0, 6.0, 5.0, 4.0]),
        _series(2, "B", [7.5, 7.0, 6.5, 6.0, 5.5]),
    ]
    r = compute_team_form_health(players).value
    assert r.pct_declining > 50


def test_concerns_list_declining_low_reliability():
    """Düşen + düşük reliability oyuncu concerns'e girer."""
    players = [
        _series(1, "Star", [8] * 10),
        _series(2, "Worry", [5, 4.5, 4, 3.5, 3, 2.5, 2]),
    ]
    r = compute_team_form_health(players).value
    concern_names = [s.name for s in r.concerns]
    assert "Worry" in concern_names


def test_top_performers_capped_at_3():
    players = [_series(i, f"P{i}", [7.0 + i * 0.1] * 5) for i in range(5)]
    r = compute_team_form_health(players).value
    assert len(r.top_performers) <= 3


def test_empty_players():
    r = compute_team_form_health([]).value
    assert r.player_count == 0
    assert r.team_health_score == 0.0


def test_player_with_empty_ratings_skipped():
    players = [
        _series(1, "OK", [7] * 5),
        _series(2, "Empty", []),
    ]
    r = compute_team_form_health(players).value
    assert r.player_count == 1
    assert any("Empty" in n for n in r.notes)


def test_team_avg_rating_correct():
    players = [
        _series(1, "A", [8.0] * 5),
        _series(2, "B", [6.0] * 5),
    ]
    r = compute_team_form_health(players).value
    assert abs(r.team_avg_rating - 7.0) < 0.01


def test_pct_sum_to_approx_100():
    players = [
        _series(1, "Up", [5, 6, 7, 8, 9]),
        _series(2, "Down", [9, 8, 7, 6, 5]),
        _series(3, "Flat", [7] * 5),
        _series(4, "Flat2", [7] * 5),
    ]
    r = compute_team_form_health(players).value
    total = r.pct_improving + r.pct_declining + r.pct_stable
    assert 99.0 <= total <= 101.0


def test_high_consistency_percentage():
    players = [
        _series(1, "Consistent", [7.0, 7.05, 6.95, 7.0, 7.0]),
        _series(2, "Volatile", [3, 9, 4, 8, 5]),
    ]
    r = compute_team_form_health(players).value
    assert r.pct_high_consistency > 0
    assert r.pct_volatile > 0


def test_audit_complete():
    players = [_series(1, "A", [7] * 5), _series(2, "B", [6] * 5)]
    res = compute_team_form_health(players)
    a = res.audit.value
    assert "player_count" in a
    assert "team_health_score" in a
    assert "directions" in a
    assert "top_names" in a


def test_summary_includes_health_and_verdict():
    players = [_series(i, f"P{i}", [7.5] * 5) for i in range(3)]
    r = compute_team_form_health(players).value
    assert "health" in r.summary.lower()
    assert "kadronun" in r.summary.lower() or "kadro" in r.summary.lower()


def test_snapshots_have_all_players():
    players = [_series(i, f"P{i}", [7.0] * 5) for i in range(4)]
    r = compute_team_form_health(players).value
    assert len(r.snapshots) == 4
    names = {s.name for s in r.snapshots}
    assert names == {"P0", "P1", "P2", "P3"}
