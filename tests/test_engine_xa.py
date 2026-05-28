"""engine.xa — Expected Assists tests."""

from __future__ import annotations

from app.domain import PassEvent, Shot
from app.engine.xa import compute_player_xa


def _shot(**kw) -> Shot:
    base = dict(
        sport="football", match_external_id=1, player_external_id=99,
        minute=20.0, x=88.0, y=50.0, body_part="right_foot",
        pattern="open_play", is_goal=False,
    )
    base.update(kw)
    return Shot(**base)  # type: ignore[arg-type]


def _pass(
    pid: int, minute: float = 20.0, key_pass: bool = False, assist: bool = False,
    *, completed: bool = True,
) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=1,
        player_external_id=pid, team_external_id=1,
        minute=minute, period=1,
        start_x=70.0, start_y=50.0, end_x=85.0, end_y=50.0,
        completed=completed,
        key_pass=key_pass, assist=assist,
    )


def test_key_pass_followed_by_shot_adds_xa():
    """Bir key_pass + 5 sn içinde şut → xA pozitif."""
    p = _pass(1, minute=20.0, key_pass=True)
    s = _shot(minute=20.05)  # 3 saniye sonra
    r = compute_player_xa(1, [p], [s], minutes_played=90)
    assert r.value.key_passes == 1
    assert r.value.xa_total > 0


def test_key_pass_without_shot_no_xa():
    """Şut yoksa xA eklenmez."""
    p = _pass(1, minute=20.0, key_pass=True)
    r = compute_player_xa(1, [p], [], minutes_played=90)
    assert r.value.key_passes == 1
    assert r.value.xa_total == 0.0


def test_key_pass_with_late_shot_excluded():
    """Şut window dışında (10 sn sonra) — eşleşmez."""
    p = _pass(1, minute=20.0, key_pass=True)
    s = _shot(minute=20.5)  # 30 saniye sonra
    r = compute_player_xa(1, [p], [s], minutes_played=90)
    assert r.value.xa_total == 0.0


def test_non_key_pass_excluded():
    """key_pass=False olan pas xA'ya girmez."""
    p = _pass(1, minute=20.0, key_pass=False)
    s = _shot(minute=20.05)
    r = compute_player_xa(1, [p], [s], minutes_played=90)
    assert r.value.key_passes == 0
    assert r.value.xa_total == 0.0


def test_goal_assist_increments_goals_assisted():
    p = _pass(1, minute=20.0, assist=True)
    s = _shot(minute=20.05, is_goal=True)
    r = compute_player_xa(1, [p], [s], minutes_played=90)
    assert r.value.goals_assisted == 1


def test_per_90_normalization():
    """45 dk oyuncuda per_90 toplam xA'nın 2 katı."""
    p = _pass(1, minute=20.0, key_pass=True)
    s = _shot(minute=20.05)
    r = compute_player_xa(1, [p], [s], minutes_played=45)
    assert abs(r.value.xa_per_90 - r.value.xa_total * 2) < 1e-3


def test_other_player_excluded():
    p1 = _pass(1, minute=20.0, key_pass=True)
    p2 = _pass(2, minute=20.0, key_pass=True)
    s = _shot(minute=20.05)
    r = compute_player_xa(1, [p1, p2], [s], minutes_played=90)
    assert r.value.key_passes == 1


def test_audit_records_window():
    r = compute_player_xa(1, [], [], minutes_played=90)
    assert r.audit.engine == "engine.xa"
    assert "shot_assist_window_seconds" in r.audit.inputs
