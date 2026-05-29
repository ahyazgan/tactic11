"""Sprint 3 endpoint smoke testleri — transfer-targets + rehab CRUD-lite
(Faz 5 #35, #43).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.sprint3 import (
    RehabPayload,
    create_rehab,
    list_active_rehab,
    transfer_targets,
)
from app.db.base import Base
from app.db import models
from app.sports import football


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_player(
    session: Session, *,
    player_id: int, position: str | None = None, birth: date | None = None,
) -> None:
    session.add(models.Player(
        sport=football.SPORT_NAME,
        external_id=player_id,
        name=f"Player {player_id}",
        position=position,
        birth_date=birth,
    ))
    session.flush()


def _seed_appearance(
    session: Session, *,
    player_id: int, match_id: int, minutes: int = 90,
    rating: float | None = None,
    kickoff: datetime | None = None,
) -> None:
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        minutes=minutes,
        kickoff=kickoff or datetime.now(UTC),
        rating_apifootball=rating,
    ))
    session.flush()


# --------------------------------------------------------------------------- #
# Transfer targets (#35)
# --------------------------------------------------------------------------- #


def test_transfer_targets_404_when_target_has_no_appearance(
    session: Session,
) -> None:
    with pytest.raises(HTTPException) as exc:
        transfer_targets(target_player_id=999, session=session)
    assert exc.value.status_code == 404


def test_transfer_targets_position_filter(session: Session) -> None:
    today = datetime.now(UTC).date()
    # Target — MF
    _seed_player(session, player_id=1, position=football.POSITION_MIDFIELDER,
                 birth=date(1998, 1, 1))
    for m in range(10):
        _seed_appearance(session, player_id=1, match_id=m, minutes=90, rating=7.0)

    # Aday 2 — MF (uygun)
    _seed_player(session, player_id=2, position=football.POSITION_MIDFIELDER,
                 birth=date(2000, 1, 1))
    for m in range(20, 30):
        _seed_appearance(session, player_id=2, match_id=m, minutes=90, rating=7.2)

    # Aday 3 — Forward (filtreyle dışarı)
    _seed_player(session, player_id=3, position=football.POSITION_FORWARD,
                 birth=date(1999, 1, 1))
    for m in range(40, 50):
        _seed_appearance(session, player_id=3, match_id=m, minutes=90, rating=7.5)

    out = transfer_targets(
        target_player_id=1, position=football.POSITION_MIDFIELDER,
        min_minutes=270, top_n=5, session=session,
    )
    assert out.target_player_external_id == 1
    pids = {m.player_external_id for m in out.matches}
    assert 2 in pids
    assert 3 not in pids   # forward filtrelendi


def test_transfer_targets_max_age_filter(session: Session) -> None:
    today = datetime.now(UTC).date()
    _seed_player(session, player_id=1, position=football.POSITION_DEFENDER,
                 birth=date(today.year - 25, 1, 1))
    for m in range(10):
        _seed_appearance(session, player_id=1, match_id=m, minutes=90)

    _seed_player(session, player_id=2, position=football.POSITION_DEFENDER,
                 birth=date(today.year - 22, 6, 1))
    for m in range(20, 30):
        _seed_appearance(session, player_id=2, match_id=m, minutes=90)

    # 35 yaş — max 25 yaş filtresiyle dışarı
    _seed_player(session, player_id=3, position=football.POSITION_DEFENDER,
                 birth=date(today.year - 35, 1, 1))
    for m in range(40, 50):
        _seed_appearance(session, player_id=3, match_id=m, minutes=90)

    out = transfer_targets(
        target_player_id=1, position=football.POSITION_DEFENDER,
        max_age=25, min_minutes=270, session=session,
    )
    pids = {m.player_external_id for m in out.matches}
    assert 2 in pids
    assert 3 not in pids
    # Yaş alanı doluyor
    if out.matches:
        assert out.matches[0].age is not None


# --------------------------------------------------------------------------- #
# Rehab CRUD-lite (#43)
# --------------------------------------------------------------------------- #


def test_create_rehab_active_then_list(session: Session) -> None:
    payload = RehabPayload(
        injury_type="hamstring grade II",
        injury_start=date.today(),
        expected_return=date.today() + timedelta(days=21),
        status="active",
        notes="MR yapıldı, hafif yırtık",
    )
    out = create_rehab(player_id=42, payload=payload, session=session)
    assert out.player_external_id == 42
    assert out.status == "active"
    assert out.injury_type.startswith("hamstring")

    active = list_active_rehab(player_id=42, session=session)
    assert len(active) == 1
    assert active[0].id == out.id


def test_create_rehab_invalid_status_rejected(session: Session) -> None:
    payload = RehabPayload(
        injury_type="muscle strain",
        injury_start=date.today(),
        status="bogus",
    )
    with pytest.raises(HTTPException) as exc:
        create_rehab(player_id=1, payload=payload, session=session)
    assert exc.value.status_code == 400


def test_cleared_rehab_excluded_from_active(session: Session) -> None:
    payload_active = RehabPayload(
        injury_type="ankle sprain",
        injury_start=date.today() - timedelta(days=14),
        status="active",
    )
    payload_cleared = RehabPayload(
        injury_type="knee meniscus",
        injury_start=date.today() - timedelta(days=120),
        actual_return=date.today() - timedelta(days=30),
        status="cleared",
    )
    create_rehab(player_id=7, payload=payload_active, session=session)
    create_rehab(player_id=7, payload=payload_cleared, session=session)

    active = list_active_rehab(player_id=7, session=session)
    assert len(active) == 1
    assert active[0].injury_type == "ankle sprain"
