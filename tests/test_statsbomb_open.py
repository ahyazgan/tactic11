"""StatsBomb Open adapter — parser doğrulama (HTTP yok)."""

from __future__ import annotations

import pytest

from app.data.sources.statsbomb_open import (
    SHOT_EVENT_TYPE_ID,
    StatsBombOpen,
    _event_to_shot,
    _is_shot_event,
    shots_from_events_json,
)

# --------------------------------------------------------------------------- #
# Sample StatsBomb event — real-shape (docs'tan basitleştirilmiş)
# --------------------------------------------------------------------------- #

SAMPLE_GOAL_SHOT = {
    "id": "abc-123",
    "minute": 33,
    "type": {"id": 16, "name": "Shot"},
    "play_pattern": {"id": 1, "name": "Regular Play"},  # open_play
    "player": {"id": 3501, "name": "Lionel Messi"},
    "location": [108, 40],  # 120x80 saha — gole yakın merkez
    "shot": {
        "outcome": {"name": "Goal"},
        "body_part": {"id": 38, "name": "Left Foot"},
        "type": {"name": "Open Play"},
    },
}

SAMPLE_MISSED_HEADER = {
    "id": "def-456",
    "minute": 67,
    "type": {"id": 16},
    "play_pattern": {"id": 4},  # corner_kick
    "player": {"id": 3502},
    "location": [105, 35],
    "shot": {
        "outcome": {"name": "Off Target"},
        "body_part": {"id": 37, "name": "Head"},
        "type": {"name": "Open Play"},
    },
}

SAMPLE_PENALTY = {
    "id": "ghi-789",
    "minute": 55,
    "type": {"id": 16},
    "play_pattern": {"id": 5},  # free_kick
    "player": {"id": 3503},
    "location": [108, 40],
    "shot": {
        "outcome": {"name": "Goal"},
        "body_part": {"id": 40, "name": "Right Foot"},
        "type": {"name": "Penalty"},
    },
}

SAMPLE_PASS_EVENT = {
    "id": "pass-1",
    "minute": 10,
    "type": {"id": 30, "name": "Pass"},
    "player": {"id": 3501},
}


# --------------------------------------------------------------------------- #
# _is_shot_event
# --------------------------------------------------------------------------- #


def test_is_shot_event_true_for_type_16():
    assert _is_shot_event(SAMPLE_GOAL_SHOT) is True


def test_is_shot_event_false_for_pass():
    assert _is_shot_event(SAMPLE_PASS_EVENT) is False


def test_is_shot_event_handles_missing_type():
    assert _is_shot_event({"id": "x"}) is False


def test_shot_event_type_id_constant():
    assert SHOT_EVENT_TYPE_ID == 16


# --------------------------------------------------------------------------- #
# _event_to_shot — parse
# --------------------------------------------------------------------------- #


def test_parse_goal_shot():
    shot = _event_to_shot(SAMPLE_GOAL_SHOT, match_id=99)
    assert shot is not None
    assert shot.match_external_id == 99
    assert shot.player_external_id == 3501
    assert shot.is_goal is True
    assert shot.pattern == "open_play"
    assert shot.body_part == "left_foot"
    # 108/120 * 100 = 90.0
    assert shot.x == 90.0
    # 40/80 * 100 = 50.0
    assert shot.y == 50.0


def test_parse_missed_header_corner():
    shot = _event_to_shot(SAMPLE_MISSED_HEADER, match_id=99)
    assert shot is not None
    assert shot.is_goal is False
    assert shot.pattern == "corner_kick"
    assert shot.body_part == "head"


def test_parse_penalty_marks_pattern():
    shot = _event_to_shot(SAMPLE_PENALTY, match_id=99)
    assert shot is not None
    assert shot.pattern == "penalty"
    assert shot.is_goal is True


def test_parse_clamps_location_to_unit_pitch():
    """Edge case: koordinat 120x80 sınırında — 100x100'e clamp."""
    ev = dict(SAMPLE_GOAL_SHOT)
    ev["location"] = [120, 80]  # tam köşe
    shot = _event_to_shot(ev, match_id=99)
    assert shot is not None
    assert shot.x == 100.0
    assert shot.y == 100.0


def test_parse_missing_location_returns_none():
    ev = dict(SAMPLE_GOAL_SHOT)
    ev["location"] = []  # boş
    shot = _event_to_shot(ev, match_id=99)
    assert shot is None


def test_parse_handles_missing_player_id():
    """player.id eksikse player_external_id=0 olur (parse fail değil)."""
    ev = dict(SAMPLE_GOAL_SHOT)
    ev["player"] = {}  # id yok
    shot = _event_to_shot(ev, match_id=99)
    assert shot is not None
    assert shot.player_external_id == 0


# --------------------------------------------------------------------------- #
# shots_from_events_json — bulk parser
# --------------------------------------------------------------------------- #


def test_shots_from_events_filters_non_shots():
    events = [SAMPLE_GOAL_SHOT, SAMPLE_PASS_EVENT, SAMPLE_PENALTY]
    shots = shots_from_events_json(events, match_id=99)
    assert len(shots) == 2  # pass hariç
    goal_count = sum(1 for s in shots if s.is_goal)
    assert goal_count == 2


def test_shots_from_events_skips_unparseable():
    bad_event = {"type": {"id": 16}, "location": []}  # missing location
    events = [SAMPLE_GOAL_SHOT, bad_event, SAMPLE_PENALTY]
    shots = shots_from_events_json(events, match_id=99)
    assert len(shots) == 2  # bad atlandı


# --------------------------------------------------------------------------- #
# StatsBombOpen.get_shots_for_match (monkeypatched fetch)
# --------------------------------------------------------------------------- #


def test_get_shots_for_match_uses_fetch_json(monkeypatch):
    """get_events monkeypatched → get_shots_for_match parser çalışıyor."""
    events = [SAMPLE_GOAL_SHOT, SAMPLE_PASS_EVENT, SAMPLE_MISSED_HEADER]
    adapter = StatsBombOpen()
    monkeypatch.setattr(adapter, "_fetch_json", lambda path: events)
    shots = adapter.get_shots_for_match(99)
    assert len(shots) == 2
    patterns = {s.pattern for s in shots}
    assert "open_play" in patterns
    assert "corner_kick" in patterns


def test_get_shots_for_match_returns_empty_when_no_shots(monkeypatch):
    adapter = StatsBombOpen()
    monkeypatch.setattr(adapter, "_fetch_json", lambda path: [SAMPLE_PASS_EVENT])
    shots = adapter.get_shots_for_match(99)
    assert shots == []


def test_fetch_json_raises_on_404(monkeypatch):
    """HTTP 4xx → RuntimeError (no retry)."""
    import httpx

    class _Fake:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            class _R:
                status_code = 404
                text = "not found"

            return _R()

    monkeypatch.setattr(httpx, "Client", _Fake)
    adapter = StatsBombOpen()
    with pytest.raises(RuntimeError, match="HTTP 404"):
        adapter._fetch_json("competitions.json")
