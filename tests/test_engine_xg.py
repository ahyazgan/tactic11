"""engine.xg — geometrik baseline xG."""

from __future__ import annotations

import pytest

from app.domain import Shot
from app.engine.xg import compute_shot_xg, compute_team_xg


def _shot(**kw) -> Shot:
    base = dict(
        sport="football", match_external_id=1, player_external_id=10,
        minute=20.0, x=85.0, y=50.0, body_part="right_foot",
        pattern="open_play", is_goal=False,
    )
    base.update(kw)
    return Shot(**base)  # type: ignore[arg-type]


def test_close_central_shot_high_xg():
    """Penaltı noktasına yakın (x=88, y=50) → xG > 0.3."""
    r = compute_shot_xg(_shot(x=88.0, y=50.0))
    assert r.value.xg > 0.3
    assert r.value.distance < 13.0
    assert r.value.angle_radians > 0.5  # geniş açı


def test_distant_shot_low_xg():
    """Orta sahaya yakın şut (x=50, y=50) → xG < 0.05."""
    r = compute_shot_xg(_shot(x=50.0, y=50.0))
    assert r.value.xg < 0.05


def test_tight_angle_shot_low_xg():
    """Köşe çizgisinden şut (x=95, y=10) → açı küçük → xG düşük."""
    r = compute_shot_xg(_shot(x=95.0, y=10.0))
    assert r.value.xg < 0.20
    assert r.value.angle_radians < 0.5


def test_penalty_is_constant():
    """Penalty xG sabit 0.76 (literatür)."""
    r = compute_shot_xg(_shot(x=88.0, y=50.0, pattern="penalty"))
    assert r.value.xg == 0.76


def test_header_penalty_lower_than_foot():
    """Kafa şutu aynı pozisyondan ayak şutundan daha az xG."""
    foot = compute_shot_xg(_shot(x=88.0, y=50.0, body_part="right_foot"))
    head = compute_shot_xg(_shot(x=88.0, y=50.0, body_part="head"))
    assert head.value.xg < foot.value.xg


def test_fast_break_higher_than_set_piece():
    """Aynı pozisyondan fast_break > set_piece (uzaklık aynı, pattern modifier farkı)."""
    fast = compute_shot_xg(_shot(x=80.0, y=50.0, pattern="fast_break"))
    set_piece = compute_shot_xg(_shot(x=80.0, y=50.0, pattern="set_piece"))
    assert fast.value.xg > set_piece.value.xg


def test_team_xg_aggregates():
    shots = [
        _shot(x=88.0, y=50.0),
        _shot(x=70.0, y=40.0),
        _shot(x=92.0, y=50.0, pattern="penalty"),
    ]
    r = compute_team_xg(611, shots, goals_actual=1)
    assert r.value.shot_count == 3
    assert r.value.total_xg > 0.76  # en az penalty kadar
    assert r.value.goals_actual == 1
    # 1 gol attı ama xG > 1 ise xg_minus_goals > 0 ("şanssız")
    if r.value.total_xg > 1.0:
        assert r.value.xg_minus_goals > 0


def test_audit_records_formula():
    r = compute_shot_xg(_shot(x=85.0, y=50.0))
    assert r.audit.engine == "engine.xg"
    assert r.audit.engine_version == "2"  # v1 → v2 trained mode eklendi
    assert "sigmoid" in r.audit.formula


def test_shot_pattern_validates():
    """Pydantic literal validation: bilinmeyen pattern → ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Shot(
            sport="football", match_external_id=1, player_external_id=10,
            minute=20.0, x=85.0, y=50.0,
            pattern="totally_invalid",  # type: ignore[arg-type]
        )


def test_xg_bounded_to_unit_interval():
    """Aşırı durumlarda bile xG ∈ [0, 1]."""
    # Çok yakın + tam ortada
    r = compute_shot_xg(_shot(x=99.0, y=50.0))
    assert 0.0 <= r.value.xg <= 1.0
    # Çok uzak
    r = compute_shot_xg(_shot(x=5.0, y=50.0))
    assert 0.0 <= r.value.xg <= 1.0
    # Sınırın yanı
    r = compute_shot_xg(_shot(x=100.0, y=50.0))
    assert 0.0 <= r.value.xg <= 1.0
