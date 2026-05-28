"""StatsBomb event parser — pass, carry, defansif aksiyon."""

from __future__ import annotations

from app.data.sources.statsbomb_event_parser import (
    event_to_carry,
    event_to_defensive_action,
    event_to_pass,
    is_defensive_action_event,
    parse_all_events,
)

# --------------------------------------------------------------------------- #
# Sample events — StatsBomb real-shape
# --------------------------------------------------------------------------- #

SAMPLE_PASS = {
    "id": "p-1", "minute": 25, "period": 1,
    "type": {"id": 30, "name": "Pass"},
    "team": {"id": 11, "name": "Real Madrid"},
    "player": {"id": 5503, "name": "Modrić"},
    "location": [40, 30],
    "pass": {
        "end_location": [80, 35],
        "type": {"id": 0, "name": "Open Play"},
        "technique": {"id": 1, "name": "Through Ball"},
        "shot_assist": True,
    },
    "possession": 42,
}

SAMPLE_INCOMPLETE_PASS = {
    "id": "p-2", "minute": 30, "period": 1,
    "type": {"id": 30},
    "team": {"id": 11}, "player": {"id": 5503},
    "location": [50, 40],
    "pass": {
        "end_location": [85, 50],
        "outcome": {"id": 9, "name": "Incomplete"},
    },
    "possession": 43,
}

SAMPLE_CORNER = {
    "id": "p-3", "minute": 67, "period": 2,
    "type": {"id": 30},
    "team": {"id": 11}, "player": {"id": 5503},
    "location": [120, 0],
    "pass": {
        "end_location": [108, 35],
        "type": {"id": 61, "name": "Corner"},
        "technique": {"id": 10, "name": "Inswinging"},
    },
    "possession": 50,
}

SAMPLE_CARRY = {
    "id": "c-1", "minute": 12, "period": 1,
    "type": {"id": 43, "name": "Carry"},
    "team": {"id": 11}, "player": {"id": 5503},
    "location": [50, 40],
    "carry": {"end_location": [70, 45]},
    "possession": 40,
}

SAMPLE_INTERCEPTION = {
    "id": "d-1", "minute": 15, "period": 1,
    "type": {"id": 10, "name": "Interception"},
    "team": {"id": 11}, "player": {"id": 5601},
    "location": [60, 40],
    "possession": 41,
}

SAMPLE_TACKLE_WON = {
    "id": "d-2", "minute": 18, "period": 1,
    "type": {"id": 4, "name": "Duel"},
    "team": {"id": 11}, "player": {"id": 5602},
    "location": [55, 45],
    "duel": {"outcome": {"name": "Won"}},
    "possession": 42,
}

SAMPLE_PASS_TYPE_EVENT = {  # not a defensive event
    "id": "x-1", "minute": 5, "period": 1,
    "type": {"id": 30}, "team": {"id": 11}, "player": {"id": 1},
    "location": [10, 10],
    "pass": {"end_location": [20, 20]},
}


# --------------------------------------------------------------------------- #
# Pass parse
# --------------------------------------------------------------------------- #


def test_parse_pass_basic():
    p = event_to_pass(SAMPLE_PASS, match_id=99)
    assert p is not None
    assert p.player_external_id == 5503
    assert p.team_external_id == 11
    assert p.completed is True
    assert p.key_pass is True  # shot_assist
    assert p.minute == 25.0
    assert p.period == 1
    # 40/120 * 100 = 33.33; 80/120 * 100 = 66.67
    assert abs(p.start_x - 33.33) < 0.1
    assert abs(p.end_x - 66.67) < 0.1


def test_parse_incomplete_pass():
    p = event_to_pass(SAMPLE_INCOMPLETE_PASS, match_id=99)
    assert p is not None
    assert p.completed is False


def test_parse_corner_pass_type():
    p = event_to_pass(SAMPLE_CORNER, match_id=99)
    assert p is not None
    assert p.pass_type == "corner"
    assert p.technique == "inswinger"


def test_pass_through_ball_detection():
    """Through ball technique algılansın."""
    p = event_to_pass(SAMPLE_PASS, match_id=99)
    assert p is not None
    assert p.technique == "through_ball"


def test_event_without_pass_block_returns_none():
    """Pass event olmayan input → None."""
    p = event_to_pass({"type": {"id": 16}}, match_id=99)
    assert p is None


# --------------------------------------------------------------------------- #
# Carry parse
# --------------------------------------------------------------------------- #


def test_parse_carry():
    c = event_to_carry(SAMPLE_CARRY, match_id=99)
    assert c is not None
    assert c.player_external_id == 5503
    # 50→70 in 120-pitch → ~41.67→58.33
    assert abs(c.start_x - 41.67) < 0.1
    assert abs(c.end_x - 58.33) < 0.1


def test_non_carry_event_returns_none():
    c = event_to_carry(SAMPLE_PASS, match_id=99)
    assert c is None


# --------------------------------------------------------------------------- #
# Defensive action parse
# --------------------------------------------------------------------------- #


def test_interception_is_defensive_action():
    assert is_defensive_action_event(SAMPLE_INTERCEPTION) is True
    d = event_to_defensive_action(SAMPLE_INTERCEPTION, match_id=99)
    assert d is not None
    assert d.action_type == "interception"


def test_tackle_won_is_defensive_action():
    assert is_defensive_action_event(SAMPLE_TACKLE_WON) is True
    d = event_to_defensive_action(SAMPLE_TACKLE_WON, match_id=99)
    assert d is not None
    assert d.action_type == "tackle"


def test_tackle_lost_is_not_defensive_action():
    """Duel ama outcome.name=Lost → defansif aksiyon değil."""
    losing = {**SAMPLE_TACKLE_WON, "duel": {"outcome": {"name": "Lost"}}}
    assert is_defensive_action_event(losing) is False


def test_pass_is_not_defensive_action():
    assert is_defensive_action_event(SAMPLE_PASS_TYPE_EVENT) is False


# --------------------------------------------------------------------------- #
# Bulk parser
# --------------------------------------------------------------------------- #


def test_parse_all_events_separates_types():
    events = [SAMPLE_PASS, SAMPLE_CARRY, SAMPLE_INTERCEPTION, SAMPLE_TACKLE_WON]
    result = parse_all_events(events, match_id=99)
    assert len(result["passes"]) == 1
    assert len(result["carries"]) == 1
    assert len(result["defensive_actions"]) == 2  # interception + tackle


def test_parse_all_events_handles_empty():
    result = parse_all_events([], match_id=99)
    assert result == {"shots": [], "passes": [], "carries": [], "defensive_actions": []}


def test_pass_handles_missing_end_location():
    """End location yok → None döner (parse fail değil error)."""
    bad = {
        "type": {"id": 30}, "team": {"id": 1}, "player": {"id": 1},
        "location": [50, 50], "pass": {},  # end_location yok
    }
    p = event_to_pass(bad, match_id=99)
    assert p is None
