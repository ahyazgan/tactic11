"""engine.set_piece_pattern_history tests."""

from __future__ import annotations

from app.domain import Shot
from app.engine.set_piece_pattern_history import compute_set_piece_pattern_history


def _shot(x: float, y: float, pattern: str = "corner_kick",
          is_goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=99, player_external_id=1,
        minute=10.0, x=x, y=y, pattern=pattern,  # type: ignore[arg-type]
        is_goal=is_goal,
    )


def test_most_frequent_zone_detected():
    """7 şutun 5'i central_6yd, 2'si near_post → most_frequent=central."""
    shots = [_shot(96, 50) for _ in range(5)] + [_shot(92, 20) for _ in range(2)]
    r = compute_set_piece_pattern_history(11, shots, matches_analyzed=5).value
    assert r.most_frequent_zone == "central_6yd"
    assert r.zone_frequencies["central_6yd"] == 5
    assert r.zone_frequencies["near_post"] == 2


def test_most_dangerous_zone_by_conversion():
    """near_post: 1/2 gol; central: 0/5 → most_dangerous=near_post."""
    shots = (
        [_shot(96, 50, is_goal=False) for _ in range(5)]      # 0/5
        + [_shot(92, 20, is_goal=True), _shot(92, 20, is_goal=False)]  # 1/2
    )
    r = compute_set_piece_pattern_history(11, shots, matches_analyzed=5).value
    assert r.most_dangerous_zone == "near_post"


def test_alert_text_includes_zone_in_turkish():
    shots = [_shot(96, 50, is_goal=True) for _ in range(3)]
    r = compute_set_piece_pattern_history(11, shots, matches_analyzed=5).value
    # Türkçe etiket
    assert "kale ağzı" in r.alert_text or "central" in r.alert_text


def test_insufficient_data():
    r = compute_set_piece_pattern_history(11, [], matches_analyzed=0).value
    assert r.most_frequent_zone == "insufficient_data"
    assert "Yeterli set-piece veri yok" in r.alert_text


def test_open_play_excluded():
    """Open-play shot sayılmaz."""
    shots = [_shot(96, 50, pattern="open_play", is_goal=True)]
    r = compute_set_piece_pattern_history(11, shots, matches_analyzed=1).value
    assert r.total_set_piece_shots == 0


def test_audit_includes_alert():
    shots = [_shot(96, 50)]
    r = compute_set_piece_pattern_history(11, shots, matches_analyzed=1)
    assert "alert_text" in r.audit.value
