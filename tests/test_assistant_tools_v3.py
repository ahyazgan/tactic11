"""tools_v3 register + smoke testleri (Faz 5 Sprint 2-5)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.assistant.tools import execute_tool, get_tool_schemas
from app.assistant.tools_v3 import V3_TOOL_HANDLERS, V3_TOOL_SCHEMAS
from app.db import models
from app.db.base import Base
from app.db.tenant_context import DEFAULT_TENANT_ID
from app.sports import football

# --------------------------------------------------------------------------- #
# Register doğrulama
# --------------------------------------------------------------------------- #


def test_v3_handlers_and_schemas_match() -> None:
    schema_names = {s["name"] for s in V3_TOOL_SCHEMAS}
    handler_names = set(V3_TOOL_HANDLERS.keys())
    assert schema_names == handler_names, (
        f"schema ↔ handler eşleşmiyor: {schema_names ^ handler_names}"
    )
    assert len(V3_TOOL_SCHEMAS) == 6


def test_v3_schemas_have_required_fields() -> None:
    for s in V3_TOOL_SCHEMAS:
        assert "name" in s
        assert "description" in s
        assert "input_schema" in s
        assert s["input_schema"]["type"] == "object"
        assert "properties" in s["input_schema"]
        # Her tool en az 1 required parametre tanımlamalı
        assert s["input_schema"].get("required"), s["name"]


def test_v3_schemas_merged_into_get_tool_schemas() -> None:
    all_schemas = get_tool_schemas()
    names = {s["name"] for s in all_schemas}
    # 6 v3 tool tamamı master listede
    for s in V3_TOOL_SCHEMAS:
        assert s["name"] in names


# --------------------------------------------------------------------------- #
# Smoke — execute_tool fallback v3'e iniyor + boş DB'de info döner
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_appearance(
    session: Session, *,
    player_id: int, team_id: int, match_id: int,
    minutes: int = 90,
    kickoff: datetime | None = None,
) -> None:
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        team_external_id=team_id,
        minutes=minutes,
        kickoff=kickoff or datetime.now(UTC),
    ))
    session.flush()


def test_execute_tool_routes_v3_proactive_alerts_empty(session: Session) -> None:
    raw = execute_tool(session, "get_proactive_alerts", {"team_external_id": 11})
    payload = json.loads(raw)
    assert "info" in payload


def test_execute_tool_routes_v3_rotation_plan_empty(session: Session) -> None:
    raw = execute_tool(session, "get_rotation_plan", {"team_external_id": 11})
    payload = json.loads(raw)
    assert "info" in payload


def test_execute_tool_routes_v3_injury_risk_no_apps(session: Session) -> None:
    raw = execute_tool(session, "get_injury_risk", {"player_external_id": 999})
    payload = json.loads(raw)
    assert "info" in payload


def test_execute_tool_routes_v3_squad_depth_with_squad(session: Session) -> None:
    raw = execute_tool(session, "get_squad_depth", {
        "team_external_id": 11,
        "squad": [
            {"player_id": 1, "position": football.POSITION_GOALKEEPER, "age": 28},
            {"player_id": 2, "position": football.POSITION_DEFENDER, "age": 24},
            {"player_id": 3, "position": football.POSITION_DEFENDER, "age": 32},
            {"player_id": 4, "position": football.POSITION_MIDFIELDER, "age": 27},
            {"player_id": 5, "position": football.POSITION_FORWARD, "age": 29},
        ],
    })
    payload = json.loads(raw)
    assert payload["team_external_id"] == 11
    assert payload["total_players"] == 5
    assert "by_position" in payload


def test_execute_tool_routes_v3_available_squad_with_squad(session: Session) -> None:
    raw = execute_tool(session, "get_available_squad", {
        "team_external_id": 11,
        "squad": [
            {"player_id": 1, "injured": True},
            {"player_id": 2, "suspended": True},
            {"player_id": 3, "risk_level": "extreme"},
            {"player_id": 4, "risk_level": "low"},
        ],
    })
    payload = json.loads(raw)
    assert payload["total_squad"] == 4
    assert payload["unavailable_count"] == 2  # sakat + cezalı
    assert payload["doubtful_count"] == 1     # extreme
    assert payload["available_count"] == 1


def test_execute_tool_routes_v3_rotation_plan_with_appearances(
    session: Session,
) -> None:
    # Tenant tutarlılığı: insert auto-fill + query filtresi aynı tenant'ı
    # kullansın (yoksa appearance'lar bulunamaz → loads boş).
    session.info["tenant_id"] = DEFAULT_TENANT_ID
    # 1 oyuncu, yüksek yük (270+ dk/hafta) → extreme/high
    now = datetime.now(UTC)
    for _i, m_id in enumerate([100, 101, 102, 103, 104]):
        _seed_appearance(
            session, player_id=7, team_id=11, match_id=m_id,
            minutes=90, kickoff=now,
        )
    raw = execute_tool(session, "get_rotation_plan", {
        "team_external_id": 11,
        "upcoming_matches": 3,
        "dense_schedule": True,
    })
    payload = json.loads(raw)
    assert "team_external_id" in payload, f"beklenmeyen payload: {payload}"
    assert payload["team_external_id"] == 11
    assert "candidates" in payload
    assert payload["upcoming_matches"] == 3


def test_execute_tool_unknown_tool() -> None:
    # session yok ama path tetiklenmez (handler bulunamıyor)
    raw = execute_tool(None, "get_nonexistent_tool", {})  # type: ignore[arg-type]
    payload = json.loads(raw)
    assert "error" in payload
    assert "bilinmeyen tool" in payload["error"]
