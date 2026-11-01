"""Canlı servis → WS snapshot köprüsü."""

from __future__ import annotations

import json
from pathlib import Path

from app.api import live_service_bridge
from app.data.sources import live_service
from app.data.sources.live_service import LiveServicePoller, ServiceEvent, parse_sportmonks
from tests.test_api_live_websocket import _seed_match_with_events, client  # noqa: F401

FIXTURE = Path(__file__).parent / "fixtures" / "live_sportmonks_19722767.json"


class _Static:
    provider = "sportmonks"

    def __init__(self) -> None:
        self.snap = parse_sportmonks(json.loads(FIXTURE.read_text(encoding="utf-8")))

    def fetch(self, fixture_id: int):
        return self.snap


def test_service_block_waiting_then_filled() -> None:
    poller = LiveServicePoller(_Static(), 1)
    assert live_service_bridge.service_block(poller)["status"] == "waiting"
    poller.poll()
    block = live_service_bridge.service_block(poller)
    assert block["score"] == [1, 2] and block["status"] == "finished"
    assert block["possession_total"] == [39.0, 61.0]
    assert block["possession_last_10_home"] is None  # tek örnek: pencere payı yok
    assert len(block["events"]) == 17


def test_service_alerts_speak_from_my_side() -> None:
    fresh = [ServiceEvent("goal", 12, team=0, player="A"), ServiceEvent("red", 50, team=1, player="B"),
             ServiceEvent("substitution", 60, team=0, player="C", related_player="D"),
             ServiceEvent("var", 61)]
    alerts = live_service_bridge.service_alerts(fresh, my_side=0)
    assert [a["severity"] for a in alerts] == ["warning", "critical", "info"]
    assert alerts[0]["message"] == "12' Biz gol: A"
    assert "Rakip kırmızı kart" in alerts[1]["message"]
    assert "C girdi, D çıktı" in alerts[2]["message"]


def test_merge_alerts_recounts_and_orders() -> None:
    block = {"alerts": [{"severity": "info", "message": "x"}], "total": 1, "critical": 0, "warning": 0, "info": 1}
    live_service_bridge.merge_alerts(block, [{"severity": "critical", "message": "y"}])
    assert [a["message"] for a in block["alerts"]] == ["y", "x"]
    assert (block["total"], block["critical"], block["info"]) == (2, 1, 1)


def test_websocket_takes_score_and_events_from_service(session, client, monkeypatch):  # noqa: F811
    _seed_match_with_events(session)
    monkeypatch.setattr(live_service, "make_live_service", lambda provider: _Static())
    with client.websocket_connect(
        "/ws/matches/7001/live?my_team_id=11&interval_seconds=5&max_minute=10&tenant_id=t-default"
        "&service=sportmonks&service_fixture=19722767",
    ) as ws:
        data = json.loads(ws.receive_text())
    assert data["service"]["provider"] == "sportmonks"
    assert data["score"] == "1-2"  # skorun kaynağı servis
    kinds = {a["type"] for a in data["live_alerts"]["alerts"]}
    assert {"service_goal", "service_own_goal", "service_substitution"} <= kinds
