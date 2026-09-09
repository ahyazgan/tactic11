"""engine.decision_impact — karar öncesi/sonrası etki ölçümü + karar defteri."""
from __future__ import annotations

import pytest

from app.domain import Carry, DefensiveAction, PassEvent, Shot
from app.engine.decision_impact import (
    DecisionContext,
    compute_decision_impact,
    compute_decision_track_record,
)

US, THEM = 11, 22
MATCH = 500


def _pass(minute: float, team: int, *, end_x: float = 80.0, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=MATCH, player_external_id=1, team_external_id=team,
        minute=minute, period=2, start_x=50.0, start_y=50.0, end_x=end_x, end_y=50.0,
        completed=completed,
    )


def _carry(minute: float, team: int) -> Carry:
    return Carry(
        sport="football", match_external_id=MATCH, player_external_id=1, team_external_id=team,
        minute=minute, period=2, start_x=50.0, start_y=50.0, end_x=70.0, end_y=50.0,
    )


def _shot(minute: float, team: int, *, x: float = 88.0, goal: bool = False) -> Shot:
    return Shot(
        sport="football", match_external_id=MATCH, player_external_id=1, minute=minute,
        x=x, y=50.0, is_goal=goal, team_external_id=team,
    )


def _def(minute: float, team: int) -> DefensiveAction:
    return DefensiveAction(
        sport="football", match_external_id=MATCH, player_external_id=1, team_external_id=team,
        minute=minute, period=2, x=60.0, y=50.0, action_type="pressure",
    )


def _ctx(minute: float = 60.0, dtype: str = "substitution", did: int = 1) -> DecisionContext:
    return DecisionContext(
        decision_id=did, match_external_id=MATCH, team_external_id=US,
        opponent_external_id=THEM, minute=minute, decision_type=dtype,
    )


def _events(pre_shots_us: int, post_shots_us: int, *, pre_shots_them: int = 0,
            post_shots_them: int = 0, center: float = 60.0):
    """`center` dakikasındaki karar çevresinde 15+15 dk pencere dolduran olaylar."""
    passes = [_pass(center - 10 + i * 0.5, US) for i in range(20)]
    passes += [_pass(center + i * 0.5, US) for i in range(20)]
    carries = [_carry(center - 10 + i, US) for i in range(10)] + [_carry(center + 1 + i, US) for i in range(10)]
    shots = (
        [_shot(center - 12 + i, US) for i in range(pre_shots_us)]
        + [_shot(center + 1 + i, US) for i in range(post_shots_us)]
        + [_shot(center - 11 + i, THEM) for i in range(pre_shots_them)]
        + [_shot(center + 2 + i, THEM) for i in range(post_shots_them)]
    )
    defs = [_def(center - 10 + i, US) for i in range(8)] + [_def(center + 1 + i, US) for i in range(8)]
    return passes, carries, shots, defs


def test_impact_positive_when_xg_and_xt_improve() -> None:
    passes, carries, shots, defs = _events(pre_shots_us=1, post_shots_us=6)
    r = compute_decision_impact(
        _ctx(), passes=passes, carries=carries, shots=shots, defensive_actions=defs,
        match_end_minute=90.0,
    )
    v = r.value
    assert v.verdict == "positive", v.verdict_reason
    assert v.xg_diff_delta > 0 and v.shots_delta > 0
    assert v.pre.minutes == 15.0 and v.post.minutes == 15.0
    assert 0 < v.confidence <= 1
    assert v.decision_label == "İkame"
    assert r.audit.subject_type == "decision" and r.audit.subject_id == 1
    assert "DAKİKA BAŞINA" in r.audit.formula


def test_impact_negative_when_opponent_takes_over() -> None:
    passes, carries, shots, defs = _events(pre_shots_us=6, post_shots_us=0, post_shots_them=6)
    # Karar sonrası bizim xT'yi de düşür: sonrası pasları rakibe ver
    passes = [p for p in passes if p.minute < 60] + [_pass(60.0 + i * 0.5, THEM) for i in range(20)]
    carries = [c for c in carries if c.minute < 60]
    v = compute_decision_impact(
        _ctx(), passes=passes, carries=carries, shots=shots, defensive_actions=defs,
        match_end_minute=90.0,
    ).value
    assert v.verdict == "negative", v.verdict_reason
    assert v.xg_diff_delta < 0 and v.xt_delta <= 0
    assert v.field_tilt_delta < 0


def test_windows_are_clipped_and_normalized_per_minute() -> None:
    """88. dk kararı: sonrası penceresi 2 dk — ham toplam değil, dakika başına."""
    passes = [_pass(75.0 + i * 0.5, US) for i in range(20)] + [_pass(88.2, US), _pass(89.0, US)]
    shots = [_shot(80.0, US), _shot(88.5, US), _shot(89.5, US)]
    v = compute_decision_impact(
        _ctx(minute=88.0), passes=passes, carries=[], shots=shots, match_end_minute=90.0,
    ).value
    assert v.post.minutes == 2.0 and v.pre.minutes == 15.0
    # 2 dakikada 2 şut → dakika başına 1.0; ham sayı olsaydı 2 olurdu
    assert v.post.shots_for == pytest.approx(1.0)
    assert v.verdict == "insufficient_data"          # 2 dk < MIN_WINDOW_MIN
    assert v.confidence == 0.0
    assert "kısa" in v.verdict_reason


def test_no_events_gives_insufficient_data() -> None:
    v = compute_decision_impact(_ctx(), passes=[], carries=[], shots=[]).value
    assert v.verdict == "insufficient_data" and v.confidence == 0.0
    assert v.pre.xg_diff == 0.0 and v.post.xg_diff == 0.0


def test_track_record_aggregates_by_type_and_band() -> None:
    passes, carries, shots, defs = _events(pre_shots_us=1, post_shots_us=6)
    good = compute_decision_impact(_ctx(minute=60.0, did=1), passes=passes, carries=carries,
                                   shots=shots, defensive_actions=defs, match_end_minute=90.0).value
    passes2, carries2, shots2, defs2 = _events(pre_shots_us=6, post_shots_us=0,
                                                post_shots_them=6, center=72.0)
    passes2 = [p for p in passes2 if p.minute < 72] + [_pass(72.0 + i * 0.5, THEM) for i in range(20)]
    bad = compute_decision_impact(_ctx(minute=72.0, dtype="formation", did=2), passes=passes2,
                                  carries=[c for c in carries2 if c.minute < 72], shots=shots2,
                                  defensive_actions=defs2, match_end_minute=90.0).value
    empty = compute_decision_impact(_ctx(minute=89.0, did=3), passes=[], carries=[], shots=[]).value

    r = compute_decision_track_record(US, [good, bad, empty])
    v = r.value
    assert v.decisions == 3 and v.measured == 2
    assert v.positive == 1 and v.negative == 1
    assert v.hit_rate == 0.5                      # ölçülemeyen paydaya girmedi
    types = {t.decision_type: t for t in v.by_type}
    assert types["substitution"].hit_rate == 1.0 and types["substitution"].label == "İkame"
    assert types["formation"].hit_rate == 0.0
    bands = {b.band: b for b in v.by_minute_band}
    assert bands["46-70"].n == 1 and bands["71-85"].n == 1
    assert v.best is not None and v.best.decision_id == 1
    assert v.worst is not None and v.worst.decision_id == 2
    assert r.audit.metric == "decision_track_record"


def test_track_record_empty_is_safe() -> None:
    v = compute_decision_track_record(US, []).value
    assert v.decisions == 0 and v.hit_rate is None and v.best is None
    assert v.by_type == () and v.by_minute_band == ()
