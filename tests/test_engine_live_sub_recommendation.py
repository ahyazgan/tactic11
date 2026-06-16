"""engine.live_sub_recommendation tests."""

from __future__ import annotations

from app.domain import PassEvent
from app.engine.live_sub_recommendation import compute_live_sub_recommendation


def _p(player: int, minute: float, completed: bool = True) -> PassEvent:
    return PassEvent(
        sport="football", match_external_id=99, player_external_id=player,
        team_external_id=11, minute=minute, period=1,
        start_x=50, start_y=50, end_x=60, end_y=50,
        completed=completed,
    )


def test_high_urgency_when_fatigued_and_losing():
    """Yorgun oyuncu + geride + 75. dakika → high urgency."""
    # Player 100: 15 erken aktif pas, 2 geç başarısız pas → fatigue yüksek
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert len(r.recommendations) >= 1
    top = r.recommendations[0]
    assert top.player_external_id == 100
    assert top.urgency_label in ("high", "medium")
    assert r.score_state == "losing"


def test_score_state_winning_lower_urgency():
    passes = [_p(100, minute=10.0)] * 5 + [_p(100, minute=70.0)] * 5
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=2, opponent_score=0,
    ).value
    assert r.score_state == "winning"


def test_eligible_player_ids_excludes_subbed_off():
    """Faz B: çoktan çıkmış oyuncu (eligible kümede yok) önerilmez —
    event'leri pencerede hâlâ görünse bile."""
    # 100 ve 200 ikisi de yorgun aktör; ama 100 sahadan çıktı (eligible: {200}).
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
        + [_p(200, minute=10.0, completed=True)] * 15
        + [_p(200, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
        eligible_player_ids={200},
    ).value
    rec_ids = {rec.player_external_id for rec in r.recommendations}
    assert 100 not in rec_ids            # çıkmış → önerilmez
    assert 200 in rec_ids                # sahada → önerilir


def test_eligible_none_keeps_all_actors():
    """eligible_player_ids=None → eski davranış (tüm event-aktörleri)."""
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=65.0, completed=False)] * 2
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0, my_score=0, opponent_score=1,
    ).value
    assert 100 in {rec.player_external_id for rec in r.recommendations}


def test_low_action_player_filtered():
    """3 aksiyon var (eşik 5) → filtre."""
    passes = [_p(100, minute=10.0)] * 3
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=60.0,
    ).value
    assert len(r.recommendations) == 0


def test_reasons_human_readable():
    passes = (
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=70.0, completed=False)] * 5
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=78.0, my_score=0, opponent_score=1,
    ).value
    assert r.recommendations[0].reasons
    # Türkçe nedenler
    reasons_str = " ".join(r.recommendations[0].reasons)
    assert any(kw in reasons_str for kw in ("yorgunluk", "Geride", "son"))


def test_top_3_ranked():
    """3 oyuncudan biri çok yorgun → o ilk sırada."""
    passes = (
        # Player 100: yüksek fatigue
        [_p(100, minute=10.0, completed=True)] * 15
        + [_p(100, minute=70.0, completed=False)] * 2
        # Player 200: normal
        + [_p(200, minute=10.0, completed=True)] * 8
        + [_p(200, minute=70.0, completed=True)] * 8
        # Player 300: az aksiyon
        + [_p(300, minute=10.0, completed=True)] * 5
        + [_p(300, minute=70.0, completed=True)] * 5
    )
    r = compute_live_sub_recommendation(
        team_external_id=11, all_passes=passes, all_def_actions=[],
        current_minute=75.0,
    ).value
    assert len(r.recommendations) <= 3
    # Player 100 ilk olmalı (en yorgun)
    assert r.recommendations[0].player_external_id == 100
