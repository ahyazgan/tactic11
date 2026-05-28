"""engine.player_role tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.engine.player_role import compute_player_role


@dataclass(frozen=True)
class _App:
    sport: str
    player_external_id: int
    match_external_id: int
    minutes: int
    kickoff: datetime
    position_played: str | None = None
    passes_total: int | None = None
    passes_accuracy: int | None = None
    shots_total: int | None = None
    dribbles_success: int | None = None
    fouls_committed: int | None = None
    fouls_drawn: int | None = None


def _app(pid: int, mins: int, **kw) -> _App:
    base = dict(
        sport="football", player_external_id=pid, match_external_id=1,
        minutes=mins, kickoff=datetime(2024, 8, 15, tzinfo=UTC),
    )
    base.update(kw)
    return _App(**base)  # type: ignore[arg-type]


def test_goalkeeper_detected():
    apps = [_app(1, 90, position_played="G", passes_total=20, passes_accuracy=85)]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "goalkeeper"


def test_ball_playing_cb():
    """CB pozisyonu + yüksek pas + yüksek accuracy → ball_playing_cb."""
    apps = [
        _app(1, 90, position_played="D",
             passes_total=60, passes_accuracy=90,
             shots_total=0, dribbles_success=0,
             fouls_committed=1, fouls_drawn=1)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "ball_playing_cb"


def test_traditional_cb():
    """CB pozisyonu + düşük pas → traditional_cb."""
    apps = [
        _app(1, 90, position_played="D",
             passes_total=30, passes_accuracy=78,
             shots_total=0, dribbles_success=0,
             fouls_committed=2, fouls_drawn=1)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "traditional_cb"


def test_target_man():
    """Forward + yüksek fouls_drawn + düşük dribble → target_man."""
    apps = [
        _app(1, 90, position_played="F",
             passes_total=15, passes_accuracy=72,
             shots_total=3, dribbles_success=1,
             fouls_committed=1, fouls_drawn=4)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "target_man"


def test_inside_forward():
    """Forward + yüksek dribble → inside_forward."""
    apps = [
        _app(1, 90, position_played="F",
             passes_total=20, passes_accuracy=78,
             shots_total=4, dribbles_success=3,
             fouls_committed=1, fouls_drawn=2)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "inside_forward"


def test_defensive_mid():
    """M + düşük şut + yüksek fouls_committed → defensive_mid."""
    apps = [
        _app(1, 90, position_played="M",
             passes_total=50, passes_accuracy=85,
             shots_total=0, dribbles_success=1,
             fouls_committed=2, fouls_drawn=1)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "defensive_mid"


def test_deep_playmaker():
    """M + yüksek pas + yüksek accuracy + düşük şut → deep_playmaker."""
    apps = [
        _app(1, 90, position_played="M",
             passes_total=80, passes_accuracy=92,
             shots_total=1, dribbles_success=1,
             fouls_committed=1, fouls_drawn=2)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "deep_playmaker"


def test_box_to_box_default_for_midfielder():
    """M + orta-seviye herşey → box_to_box (default)."""
    apps = [
        _app(1, 90, position_played="M",
             passes_total=45, passes_accuracy=82,
             shots_total=1, dribbles_success=1,
             fouls_committed=1, fouls_drawn=1)
        for _ in range(3)
    ]
    r = compute_player_role(1, apps)
    assert r.value.primary_role == "box_to_box"


def test_empty_appearances_unknown():
    r = compute_player_role(999, [])
    assert r.value.primary_role == "unknown"
    assert r.value.confidence == 0.0


def test_audit_records_thresholds():
    apps = [_app(1, 90, position_played="M", passes_total=80, passes_accuracy=90, shots_total=1)]
    r = compute_player_role(1, apps)
    assert r.audit.engine == "engine.player_role"
    assert "primary_role" in r.audit.value
