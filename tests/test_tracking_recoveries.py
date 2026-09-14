"""Recoveries need sustained, observed control; subtype guesses remain forbidden."""
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.tracking import PlayerPosition, TrackingFrame
from app.tracking.recoveries import extract_recoveries


def frame(i, player=1, team=10, x=50):
    return TrackingFrame(
        sport="football", match_external_id=1, period=1, minute=i * .12 / 60,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=i * .12),
        source="video_tracking", continuity_id=0,
        ball=PlayerPosition(player_external_id=0, x=x, y=50),
        players=(PlayerPosition(player_external_id=player, team_external_id=team,
                                x=x, y=50, is_actor=True),),
    )


def recovery_stream():
    return [frame(i) if i < 4 else frame(i, 2, 20, 52) for i in range(9)]


def test_observed_recovery_has_recipient_team_and_no_invented_subtype():
    result = extract_recoveries(recovery_stream())
    assert len(result.actions) == 1
    d = result.actions[0]
    assert d.action_type == "ball_recovery" and d.estimated
    assert d.team_external_id == 20 and d.previous_team_external_id == 10
    assert d.player_external_id == 2 and d.previous_player_external_id == 1
    assert d.minute == pytest.approx(.48 / 60)
    assert d.control_seconds >= .24


@pytest.mark.parametrize("change", [{"ball": None}, {"ball_estimated": True},
                                    {"period": 2}, {"continuity_id": 1},
                                    {"match_external_id": 2}, {"minute": 2}])
def test_uncertain_ball_and_scope_breaks_do_not_create_recoveries(change):
    frames = recovery_stream()
    frames[3] = frames[3].model_copy(update=change)
    assert not extract_recoveries(frames).actions


def test_one_frame_opponent_touch_is_not_recovery():
    frames = [frame(i) for i in range(10)]
    frames[5] = frame(5, 2, 20, 52)
    assert not extract_recoveries(frames).actions


def test_same_team_change_is_only_a_pass_candidate():
    assert not extract_recoveries([frame(i) if i < 4 else frame(i, 2, 10, 52)
                                   for i in range(9)]).actions


def test_overfull_team_breaks_recovery_evidence():
    frames = recovery_stream()
    extra = tuple(PlayerPosition(player_external_id=i, team_external_id=10, x=5, y=5)
                  for i in range(100, 111))
    frames[3] = frames[3].model_copy(update={"players": frames[3].players + extra})
    assert not extract_recoveries(frames).actions
