"""contract_alerts engine + endpoint testleri (Faz 5 #34)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base
from app.engine.contract_alerts import compute_contract_alerts
from app.sports import football

# --------------------------------------------------------------------------- #
# Engine (saf)
# --------------------------------------------------------------------------- #


def test_contract_alerts_empty_input() -> None:
    r = compute_contract_alerts([], today=date(2026, 5, 29)).value
    assert r.total_contracts == 0
    assert r.in_horizon == 0
    assert r.alerts == ()


def test_contract_alerts_levels_correct() -> None:
    today = date(2026, 5, 29)
    contracts = [
        {"player_external_id": 1, "contract_end": today + timedelta(days=30)},   # critical
        {"player_external_id": 2, "contract_end": today + timedelta(days=150)},  # warning
        {"player_external_id": 3, "contract_end": today + timedelta(days=300)},  # notice (≤365)
        {"player_external_id": 4, "contract_end": today - timedelta(days=10)},   # expired
        {"player_external_id": 5, "contract_end": today + timedelta(days=500)},  # horizon dışı
    ]
    r = compute_contract_alerts(contracts, today=today, horizon_days=365).value
    assert r.total_contracts == 5
    assert r.in_horizon == 4
    assert r.critical_count == 1
    assert r.warning_count == 1
    assert r.notice_count == 1
    assert r.expired_count == 1
    # Sıralama: critical önce
    assert r.alerts[0].level == "critical"
    assert r.alerts[0].player_external_id == 1


def test_contract_alerts_horizon_filter_strict() -> None:
    today = date(2026, 5, 29)
    contracts = [
        {"player_external_id": 1, "contract_end": today + timedelta(days=180)},
        {"player_external_id": 2, "contract_end": today + timedelta(days=200)},
    ]
    r = compute_contract_alerts(contracts, today=today, horizon_days=180).value
    assert r.in_horizon == 1
    assert r.alerts[0].player_external_id == 1


def test_contract_alerts_message_includes_days() -> None:
    today = date(2026, 5, 29)
    contracts = [
        {"player_external_id": 42, "contract_end": today + timedelta(days=45)},
    ]
    r = compute_contract_alerts(contracts, today=today).value
    assert r.alerts[0].level == "critical"
    assert "45" in r.alerts[0].message
    assert "42" in r.alerts[0].message


def test_contract_alerts_expired_negative_days() -> None:
    today = date(2026, 5, 29)
    contracts = [
        {"player_external_id": 1, "contract_end": today - timedelta(days=30)},
    ]
    r = compute_contract_alerts(contracts, today=today).value
    assert r.alerts[0].level == "expired"
    assert r.alerts[0].days_remaining == -30
    assert "30 gün önce bitmiş" in r.alerts[0].message


# --------------------------------------------------------------------------- #
# Endpoint (DB + engine)
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_contract(
    session: Session, *,
    player_id: int, contract_end: date, team_id: int | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(models.PlayerContract(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        team_external_id=team_id,
        contract_end=contract_end,
        created_at=now,
        updated_at=now,
    ))
    session.flush()


def test_endpoint_contract_alerts_basic(session: Session) -> None:
    from app.api.sprint3 import list_contract_alerts
    today = datetime.now(UTC).date()
    _seed_contract(session, player_id=1, contract_end=today + timedelta(days=30), team_id=11)
    # 150 gün warning aralığında (engine spec: critical≤60, warning≤180).
    _seed_contract(session, player_id=2, contract_end=today + timedelta(days=150), team_id=11)
    out = list_contract_alerts(
        team_external_id=11, horizon_days=365, session=session,
    )
    assert out.total_contracts == 2
    assert out.in_horizon == 2
    assert out.critical_count == 1
    assert out.warning_count == 1


def test_endpoint_contract_alerts_filter_by_team(session: Session) -> None:
    from app.api.sprint3 import list_contract_alerts
    today = datetime.now(UTC).date()
    _seed_contract(session, player_id=1, contract_end=today + timedelta(days=30), team_id=11)
    _seed_contract(session, player_id=2, contract_end=today + timedelta(days=30), team_id=22)
    out = list_contract_alerts(
        team_external_id=11, horizon_days=365, session=session,
    )
    assert out.total_contracts == 1
    assert out.alerts[0].player_external_id == 1
