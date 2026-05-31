"""Transfer asistan tool'ları — get_transfer_value + get_contract_risk routing."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from app.assistant.tools import execute_tool, get_tool_schemas
from app.db import models
from app.sports import football


def _seed_player(session, pid: int = 5001, *, with_contract_days: int | None = None):
    now = datetime.now(UTC)
    session.add(models.Player(
        sport=football.SPORT_NAME, external_id=pid, name="Test Oyuncu",
        position="M", birth_date=date(now.year - 25, 1, 1),
    ))
    for i in range(12):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, player_external_id=pid,
            match_external_id=9000 + i, minutes=80,
            kickoff=now - timedelta(days=7 * i + 3),
            rating_apifootball=7.4,
        ))
    if with_contract_days is not None:
        session.add(models.PlayerContract(
            sport=football.SPORT_NAME, player_external_id=pid,
            contract_end=(now.date() + timedelta(days=with_contract_days)),
            created_at=now, updated_at=now,
        ))
    session.flush()


def test_transfer_value_tool_registered_and_routes(session):
    names = {s["name"] for s in get_tool_schemas()}
    assert "get_transfer_value" in names
    assert "get_contract_risk" in names

    _seed_player(session, 5001)
    out = json.loads(execute_tool(session, "get_transfer_value", {"player_external_id": 5001}))
    assert out["player_id"] == 5001
    assert 0.0 <= out["value_score"] <= 100.0
    assert out["tier"] in ("elite", "high", "solid", "squad", "fringe")
    assert out["age"] == 25
    assert "proxy" in out["note"].lower()


def test_transfer_value_no_appearances_info(session):
    out = json.loads(execute_tool(session, "get_transfer_value", {"player_external_id": 999999}))
    assert "info" in out


def test_contract_risk_tool_routes(session):
    _seed_player(session, 5002, with_contract_days=120)  # kısa kontrat
    out = json.loads(execute_tool(session, "get_contract_risk", {"player_external_id": 5002}))
    assert out["player_id"] == 5002
    assert out["risk_level"] in ("critical", "high", "medium", "low")
    assert out["recommendation"] in ("renew_now", "sell_to_recoup", "monitor", "let_expire")
    assert out["days_remaining"] <= 121


def test_contract_risk_no_contract_info(session):
    _seed_player(session, 5003)  # kontrat yok
    out = json.loads(execute_tool(session, "get_contract_risk", {"player_external_id": 5003}))
    assert "info" in out
