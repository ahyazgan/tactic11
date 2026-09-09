"""engine.tracking_signals — pozisyon değişiminden maç-içi karar sinyalleri."""
from __future__ import annotations

from app.engine.tracking_signals import compute_tracking_signals


def _shape(**kw):
    base = {
        "players_mean": 10.0, "width_m": 40.0, "depth_m": 30.0, "compactness_m": 14.0,
        "centroid_x": 50.0, "centroid_y": 50.0, "rear_line_x": 30.0, "front_line_x": 70.0,
        "formation": None, "formation_support": 0.0, "frames_used": 10,
    }
    base.update(kw)
    return base


def _press(index: float, *, frames: int = 10, nearest: float = 4.0):
    return {"press_index": index, "frames_used": frames, "nearest_mean_m": nearest,
            "within_5m_mean": 1.5, "team_external_id": 1}


def test_block_opened_produces_vertical_pass_signal() -> None:
    r = compute_tracking_signals(
        minute=63.0,
        our_shape=_shape(), their_shape=_shape(compactness_m=18.0),
        prev_our_shape=_shape(), prev_their_shape=_shape(compactness_m=14.0),
        frames_used=12,
    )
    v = r.value
    keys = [f.key for f in v.findings]
    assert "opponent_block_opened" in keys
    f = next(f for f in v.findings if f.key == "opponent_block_opened")
    assert "dikey pas" in f.headline and f.detail["compactness_delta_m"] == 4.0
    assert 0 < f.magnitude <= 1 and f.urgency > 0.5
    assert v.frames_used == 12 and v.note is None
    assert r.audit.engine == "engine.tracking_signals"


def test_line_pushed_and_dropped_are_distinguished() -> None:
    pushed = compute_tracking_signals(
        minute=50.0, our_shape=_shape(), their_shape=_shape(rear_line_x=40.0),
        prev_their_shape=_shape(rear_line_x=30.0), prev_our_shape=_shape(),
    ).value
    f = next(f for f in pushed.findings if f.key == "opponent_line_pushed")
    assert "arkaya derinlik" in f.headline
    assert f.detail["line_delta_m"] == 10.5      # 10 x% → 10.5 m

    dropped = compute_tracking_signals(
        minute=50.0, our_shape=_shape(), their_shape=_shape(rear_line_x=20.0),
        prev_their_shape=_shape(rear_line_x=30.0), prev_our_shape=_shape(),
    ).value
    f2 = next(f for f in dropped.findings if f.key == "opponent_line_dropped")
    assert "uzaktan şut" in f2.headline


def test_press_drop_and_opponent_high_press() -> None:
    v = compute_tracking_signals(
        minute=70.0, our_shape=_shape(), their_shape=_shape(),
        prev_our_shape=_shape(), prev_their_shape=_shape(),
        our_pressure=_press(0.30), prev_our_pressure=_press(0.70),
        their_pressure=_press(0.72),
    ).value
    keys = [f.key for f in v.findings]
    assert "our_press_dropped" in keys and "opponent_press_high" in keys
    # En acil sinyal başta
    assert v.findings[0].urgency >= v.findings[-1].urgency


def test_small_changes_produce_no_signal() -> None:
    v = compute_tracking_signals(
        minute=20.0,
        our_shape=_shape(), their_shape=_shape(compactness_m=14.5, rear_line_x=31.0),
        prev_our_shape=_shape(), prev_their_shape=_shape(),
        our_pressure=_press(0.5), prev_our_pressure=_press(0.55), their_pressure=_press(0.5),
    ).value
    assert v.findings == () and v.note is not None


def test_partial_visibility_suppresses_signals() -> None:
    """Kamera 5 oyuncu görüyorsa şekil değişimi güvenilmez — sinyal üretilmez."""
    v = compute_tracking_signals(
        minute=30.0,
        our_shape=_shape(players_mean=5.0), their_shape=_shape(players_mean=4.0, compactness_m=25.0),
        prev_their_shape=_shape(players_mean=4.0, compactness_m=14.0), prev_our_shape=_shape(players_mean=5.0),
    ).value
    assert v.findings == () and "yetersiz" in (v.note or "")
    assert v.players_seen == 5.0


def test_visibility_drift_suppresses_shape_signals_but_keeps_press() -> None:
    """8 oyuncu görülen pencere ile 12 oyuncu görülen pencerenin şekli kıyaslanamaz."""
    v = compute_tracking_signals(
        minute=45.0,
        our_shape=_shape(), their_shape=_shape(players_mean=12.0, compactness_m=20.0, rear_line_x=45.0),
        prev_our_shape=_shape(), prev_their_shape=_shape(players_mean=8.0, compactness_m=14.0, rear_line_x=30.0),
        our_pressure=_press(0.30), prev_our_pressure=_press(0.70),
    ).value
    keys = [f.key for f in v.findings]
    assert "opponent_block_opened" not in keys and "opponent_line_pushed" not in keys
    assert "our_press_dropped" in keys        # topa göreli sinyal etkilenmez
    assert "kıyaslanmadı" in (v.note or "")


def test_event_anchored_source_only_uses_ball_relative_signals() -> None:
    """StatsBomb 360: kareler topun çevresini gösterir → şekil farkı geçersiz."""
    v = compute_tracking_signals(
        minute=30.0, continuous=False,
        our_shape=_shape(), their_shape=_shape(compactness_m=20.0, rear_line_x=50.0),
        prev_our_shape=_shape(), prev_their_shape=_shape(compactness_m=14.0, rear_line_x=30.0),
        their_pressure=_press(0.8),
    ).value
    keys = [f.key for f in v.findings]
    assert keys == ["opponent_press_high"]
    assert "event-çapalı" in (v.note or "")


def test_no_tracking_data_is_safe() -> None:
    v = compute_tracking_signals(minute=10.0, our_shape=None, their_shape=None).value
    assert v.findings == () and v.note == "pozisyon verisi yok"
