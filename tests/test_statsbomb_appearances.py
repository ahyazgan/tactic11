"""appearances_from_events_json — StatsBomb Starting XI + Substitution parse.

Faz B: events JSON'undan oyuncu giriş/çıkış dakikalarını türetir (HTTP yok).
"""
from __future__ import annotations

from app.data.sources.statsbomb_open import appearances_from_events_json

TEAM_A = 217
TEAM_B = 206


def _starting_xi(team_id: int, player_ids: list[int]) -> dict:
    return {
        "type": {"id": 35, "name": "Starting XI"},
        "team": {"id": team_id},
        "minute": 0,
        "tactics": {"lineup": [{"player": {"id": pid}} for pid in player_ids]},
    }


def _sub(team_id: int, minute: int, off_id: int, on_id: int) -> dict:
    return {
        "type": {"id": 19, "name": "Substitution"},
        "team": {"id": team_id},
        "minute": minute,
        "player": {"id": off_id},
        "substitution": {"replacement": {"id": on_id}},
    }


def _by_id(rows: list[dict]) -> dict[int, dict]:
    return {r["player_external_id"]: r for r in rows}


def test_starting_xi_all_start_at_zero() -> None:
    rows = appearances_from_events_json([_starting_xi(TEAM_A, [1, 2, 3])])
    by_id = _by_id(rows)
    assert set(by_id) == {1, 2, 3}
    for pid in (1, 2, 3):
        assert by_id[pid]["start_minute"] == 0.0
        assert by_id[pid]["end_minute"] is None
        assert by_id[pid]["team_external_id"] == TEAM_A


def test_substitution_closes_off_and_opens_on() -> None:
    events = [
        _starting_xi(TEAM_A, [1, 7, 10]),
        _sub(TEAM_A, 60, off_id=7, on_id=19),
    ]
    by_id = _by_id(appearances_from_events_json(events))
    # Çıkan 7: end = 60
    assert by_id[7]["start_minute"] == 0.0
    assert by_id[7]["end_minute"] == 60.0
    # Giren 19: start = 60, açık uçlu
    assert by_id[19]["start_minute"] == 60.0
    assert by_id[19]["end_minute"] is None
    assert by_id[19]["team_external_id"] == TEAM_A
    # Dokunulmayan 10 baştan beri açık
    assert by_id[10]["start_minute"] == 0.0
    assert by_id[10]["end_minute"] is None


def test_two_teams_parsed_independently() -> None:
    events = [
        _starting_xi(TEAM_A, [1, 2]),
        _starting_xi(TEAM_B, [3, 4]),
        _sub(TEAM_B, 70, off_id=3, on_id=33),
    ]
    by_id = _by_id(appearances_from_events_json(events))
    assert by_id[1]["team_external_id"] == TEAM_A
    assert by_id[33]["team_external_id"] == TEAM_B
    assert by_id[3]["end_minute"] == 70.0


def test_malformed_events_skipped() -> None:
    events = [
        {"type": {"id": 35}, "team": {"id": TEAM_A}, "tactics": {"lineup": [{"player": {}}]}},
        {"type": {"id": 19}, "team": {"id": TEAM_A}, "minute": 80},  # replacement yok
        {"type": {"id": 16}, "team": {"id": TEAM_A}},  # shot — alakasız
    ]
    # Bozuk lineup slot'u (player.id yok) ve replacement'sız sub → boş sonuç.
    assert appearances_from_events_json(events) == []


# --- coach_moves_from_events_json — gerçek antrenör hamleleri ------------------ #

def _tactical_sub(team_id: int, minute: int, off_id: int, on_id: int, outcome: str) -> dict:
    ev = _sub(team_id, minute, off_id, on_id)
    ev["substitution"]["outcome"] = {"id": 0, "name": outcome}
    return ev


def _shift(team_id: int, minute: int, formation: int) -> dict:
    return {
        "type": {"id": 36, "name": "Tactical Shift"},
        "team": {"id": team_id},
        "minute": minute,
        "tactics": {"formation": formation},
    }


def test_coach_moves_parse_sub_shift_and_injury_flag() -> None:
    from app.data.sources.statsbomb_open import coach_moves_from_events_json

    moves = coach_moves_from_events_json([
        _shift(TEAM_B, 49, 433),
        _tactical_sub(TEAM_A, 60, 1, 2, "Tactical"),
        _tactical_sub(TEAM_A, 30, 3, 4, "Injury"),
        _sub(TEAM_B, 75, 5, 6),                   # outcome alanı yok → Tactical varsayılır
        {"type": {"id": 19}, "minute": 80},        # takımsız → atlanır
        _starting_xi(TEAM_A, [1, 3]),              # hamle değil
    ])
    assert [m.minute for m in moves] == [30.0, 49.0, 60.0, 75.0]   # dakika sıralı
    injury, shift, sub, no_outcome = moves
    assert injury.kind == "substitution" and injury.tactical is False
    assert injury.player_off == 3 and injury.player_on == 4
    assert shift.kind == "tactical_shift" and shift.formation == "433" and shift.tactical
    assert sub.team_external_id == TEAM_A and sub.tactical and sub.player_off == 1
    assert no_outcome.tactical is True
