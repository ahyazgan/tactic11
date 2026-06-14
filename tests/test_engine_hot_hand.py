"""Hot Hand — sıcak el yakalama engine (G.2)."""
from __future__ import annotations

from app.domain import Shot
from app.engine.hot_hand import compute_hot_hand


def _s(team: int, minute: float, x: float = 90, y: float = 50,
       player: int = 1, pattern: str = "open_play") -> Shot:
    return Shot(
        sport="football", match_external_id=1,
        player_external_id=player, team_external_id=team,
        minute=minute, x=x, y=y, body_part="right_foot",
        pattern=pattern,  # type: ignore[arg-type]
    )


def test_no_shots_returns_zero_streak():
    r = compute_hot_hand(11, [], current_minute=70.0, window_min=15.0).value
    assert r.shots_window == 0
    assert r.hot_streak is False
    assert "şut yok" in r.tactical_advice.lower()


def test_hot_streak_when_window_above_baseline():
    """Window: 4 şut/15dk → 4.0/15; baseline: 2 şut/30dk → 1.0/15 → ratio=4.0 > 1.6."""
    shots = [
        # Baseline penceresinde 2 şut (25..55. dk)
        _s(11, 30.0, player=2),
        _s(11, 50.0, player=2),
        # Window penceresinde 4 şut (55..70)
        _s(11, 58.0, player=7), _s(11, 62.0, player=7),
        _s(11, 65.0, player=8), _s(11, 68.0, player=7),
    ]
    r = compute_hot_hand(
        11, shots, current_minute=70.0, window_min=15.0, baseline_min=30.0,
    ).value
    assert r.shots_window == 4
    assert r.shot_volume_ratio >= 1.6
    assert r.hot_streak is True
    assert r.hot_player is not None
    assert r.hot_player.player_external_id == 7  # 3 şut


def test_baseline_zero_with_window_activity_is_hot():
    shots = [
        _s(11, 62.0, player=9), _s(11, 65.0, player=9),
        _s(11, 68.0, player=10),
    ]
    r = compute_hot_hand(
        11, shots, current_minute=70.0, window_min=15.0, baseline_min=30.0,
    ).value
    assert r.shots_window == 3
    assert r.hot_streak is True
    assert r.shot_volume_ratio == 2.0


def test_few_shots_not_hot_even_with_high_ratio():
    """Window 2 şut + baseline 0 → ratio yüksek ama abs_min=3 → hot değil."""
    shots = [_s(11, 65.0), _s(11, 68.0)]
    r = compute_hot_hand(11, shots, current_minute=70.0, window_min=15.0).value
    assert r.shots_window == 2
    assert r.hot_streak is False


def test_opponent_shots_excluded():
    shots = [_s(22, 62.0), _s(22, 65.0), _s(22, 68.0)]
    r = compute_hot_hand(11, shots, current_minute=70.0).value
    assert r.shots_window == 0


def test_hot_player_with_high_xg_advice_mentions_id():
    """Aynı oyuncu 3 yakın şut → advice'da player id görünmeli."""
    shots = [
        _s(11, 60.0, player=10, x=95),
        _s(11, 62.0, player=10, x=92),
        _s(11, 65.0, player=10, x=90),
        _s(11, 68.0, player=11, x=85),
    ]
    r = compute_hot_hand(
        11, shots, current_minute=70.0, window_min=15.0, baseline_min=30.0,
    ).value
    assert r.hot_streak is True
    assert r.hot_player is not None
    assert r.hot_player.player_external_id == 10
    assert "10" in r.tactical_advice


def test_audit_record_complete():
    res = compute_hot_hand(
        11, [_s(11, 62.0), _s(11, 65.0), _s(11, 68.0)],
        current_minute=70.0,
    )
    a = res.audit.value
    assert "hot_streak" in a
    assert "shots_window" in a
    assert "shot_volume_ratio" in a
    assert "tactical_advice" in a


def test_xg_proxy_penalty_high():
    """Penaltı şutu xG proxy >= 0.7."""
    shots = [_s(11, 60.0, x=88, y=50, pattern="penalty")]
    r = compute_hot_hand(
        11, shots, current_minute=70.0, window_min=15.0,
    ).value
    assert r.xg_window >= 0.7
