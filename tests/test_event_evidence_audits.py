"""The validator itself must reject duplicate matches and wrong event endpoints."""
from types import SimpleNamespace

from scripts.audit_skillcorner_passes import strict_matches
from scripts.soccertrack_v2.audit_event_evidence import pair_events, point


def test_skillcorner_duplicate_predictions_count_once_and_late_recipient_fails():
    p = SimpleNamespace(minute=10 / 60, flight_seconds=1, from_player_external_id=1,
                        to_player_external_id=2, complete=True)
    assert strict_matches([p, p], [(90, 100, 1), (110, 120, 2)], {1: 10, 2: 10}) == (1, 1)
    assert strict_matches([p], [(90, 100, 1), (1000, 1010, 2)], {1: 10, 2: 10}) == (0, 1)


def test_soccertrack_position_and_one_to_one_constraints():
    pred = {"minute": 10, "start_x": 10, "start_y": 20, "end_x": 30, "end_y": 40,
            "team_external_id": 1, "complete": True}
    ref = {"seconds": 600, "start": [10, 20], "end": [30, 40], "team": 2, "complete": True}
    assert len(pair_events([pred, pred], [ref], {"1": 2}, full=True)) == 1
    assert not pair_events([pred], [{**ref, "end": [70, 40]}], {"1": 2}, full=True)
    assert not pair_events([pred], [ref], {"1": 1}, full=True)
    assert not pair_events([pred], [{**ref, "start": [70, 20]}], {"1": 2})


def test_player_nodes_coordinates_are_transverse_and_reversed():
    assert point({"x": ".2", "y": ".3"}) == [70, 80]
    assert point({"x": "", "y": ".3"}) is None
