"""Canlı servis katmanı: sağlayıcı ayrıştırma, pencere payı, sorgu döngüsü."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.data.sources.live_service import (
    APIFootballLive,
    LiveServicePoller,
    PossessionHistory,
    ServiceEvent,
    new_events,
    parse_api_football,
    parse_sportmonks,
)

FIXTURE = Path(__file__).parent / "fixtures" / "live_sportmonks_19722767.json"


def _sportmonks() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_sportmonks_real_fixture_parses_score_events_possession_and_periods() -> None:
    snap = parse_sportmonks(_sportmonks())
    assert (snap.home_name, snap.away_name) == ("Hibernian", "Celtic")
    assert snap.status == "finished"
    assert snap.score == (1, 2)
    assert snap.possession == (39.0, 61.0)
    assert [e.minute for e in snap.goals()] == [3, 5, 43]
    assert snap.goals()[0].team == 0 and snap.goals()[2].team == 1
    assert snap.goals()[1].kind == "own_goal"
    assert sum(e.kind == "substitution" for e in snap.events) == 9
    assert snap.period_starts[0] == datetime.fromtimestamp(1792929675, tz=UTC)
    assert len(snap.period_starts) == 2
    # uzatma dakikası sıralamaya girer: 45+1 sarı kart 43. dakika golünden sonra
    order = [e.clock_minute for e in snap.events]
    assert order == sorted(order)


def test_sportmonks_live_minute_comes_from_ticking_period() -> None:
    body = _sportmonks()
    body["data"]["state"] = {"developer_name": "INPLAY_2ND_HALF"}
    body["data"]["periods"][1].update({"ticking": True, "minutes": 67})
    snap = parse_sportmonks(body)
    assert snap.status == "live" and snap.minute == 67


def _api_football_item() -> dict:
    return {
        "fixture": {"id": 1035, "status": {"short": "2H", "elapsed": 58},
                    "periods": {"first": 1792929600, "second": 1792933500}},
        "teams": {"home": {"id": 549, "name": "Beşiktaş"}, "away": {"id": 1005, "name": "Antalyaspor"}},
        "goals": {"home": 1, "away": 1},
        "events": [
            {"time": {"elapsed": 12, "extra": None}, "team": {"id": 549}, "player": {"name": "A"},
             "assist": {"name": "B"}, "type": "Goal", "detail": "Normal Goal"},
            {"time": {"elapsed": 45, "extra": 2}, "team": {"id": 1005}, "player": {"name": "C"},
             "assist": {"name": None}, "type": "Card", "detail": "Yellow Card"},
            {"time": {"elapsed": 51, "extra": None}, "team": {"id": 1005}, "player": {"name": "D"},
             "assist": {"name": None}, "type": "Goal", "detail": "Penalty"},
            {"time": {"elapsed": 55, "extra": None}, "team": {"id": 549}, "player": {"name": "E"},
             "assist": {"name": "F"}, "type": "subst", "detail": "Substitution 1"},
        ],
        "statistics": [
            {"team": {"id": 549}, "statistics": [{"type": "Ball Possession", "value": "57%"}]},
            {"team": {"id": 1005}, "statistics": [{"type": "Ball Possession", "value": "43%"}]},
        ],
    }


def test_api_football_item_parses() -> None:
    snap = parse_api_football(_api_football_item())
    assert snap.status == "live" and snap.minute == 58
    assert snap.score == (1, 1)
    assert snap.possession == (57.0, 43.0)
    assert [e.kind for e in snap.events] == ["goal", "yellow", "penalty_goal", "substitution"]
    assert snap.events[1].clock_minute == 47
    assert snap.events[2].team == 1
    assert len(snap.period_starts) == 2


def test_api_football_live_client_uses_injected_get() -> None:
    calls = []

    def fake_get(path: str, params: dict) -> dict:
        calls.append((path, params))
        return {"response": [_api_football_item()]}

    snap = APIFootballLive(get=fake_get).fetch(1035)
    assert calls == [("fixtures", {"id": 1035})]
    assert snap.fixture_id == 1035
    with pytest.raises(ValueError):
        APIFootballLive(get=lambda p, q: {"response": []}).fetch(1)


def test_window_share_recovers_window_possession() -> None:
    # ev sahibi ilk 30 dk %40, sonraki 10 dk %70 → 40. dk birikmiş %47,5
    h = PossessionHistory()
    h.add(30, 40.0)
    h.add(40, 47.5)
    assert h.window_share(30, 40) == pytest.approx(70.0)
    assert h.window_share(0, 30) == pytest.approx(40.0)  # başlangıç = (0, 50) varsayımı t1=0'da etkisiz
    assert h.window_share(36, 40) is None  # pencere kısa


def test_window_share_ignores_out_of_order_and_bad_samples() -> None:
    h = PossessionHistory()
    h.add(None, 50)
    h.add(10, None)
    h.add(20, 55)
    h.add(15, 99)  # geri giden dakika yok sayılır
    h.add(20, 56)  # aynı dakika güncellenir
    assert h.samples == [(20.0, 56.0)]


def test_new_events_and_poller_survive_errors() -> None:
    snap = parse_sportmonks(_sportmonks())
    early = parse_sportmonks(_sportmonks())
    object.__setattr__(early, "events", snap.events[:2])
    assert new_events(early, snap) == list(snap.events[2:])

    class Flaky:
        def __init__(self) -> None:
            self.n = 0

        def fetch(self, fixture_id: int):
            self.n += 1
            if self.n == 2:
                raise RuntimeError("timeout")
            return snap

    t = [0.0]
    poller = LiveServicePoller(Flaky(), 19722767, interval_s=20, clock=lambda: t[0])
    assert poller.due()
    assert len(poller.poll()) == len(snap.events)
    assert not poller.due()
    t[0] = 25.0
    assert poller.poll() == [] and poller.last_error == "RuntimeError: timeout"
    assert poller.snapshot is snap  # son başarılı görüntü kalır
    t[0] = 50.0
    assert poller.poll() == [] and poller.last_error is None
    assert poller.history.samples == [(93.0, 39.0)]


def test_service_event_defaults() -> None:
    e = ServiceEvent("goal", 90, 3)
    assert e.clock_minute == 93 and e.team is None
