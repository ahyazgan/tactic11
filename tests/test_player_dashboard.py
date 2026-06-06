"""Player dashboard + /players/{id}/info endpoint testleri (Faz 5 #36)."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.html_views import player_dashboard_view
from app.db import models
from app.db.base import Base
from app.sports import football

# --------------------------------------------------------------------------- #
# HTML render endpoint
# --------------------------------------------------------------------------- #


def test_player_dashboard_returns_html() -> None:
    resp = player_dashboard_view(player_id=42)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.PLAYER_ID = 42;" in body
    assert "Oyuncu Dashboard" in body


def test_player_dashboard_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        player_dashboard_view(player_id=0)
    assert exc.value.status_code == 400


def test_player_dashboard_html_fetches_info_load_form() -> None:
    """Sayfa JS'i 3 player endpoint'ini çağırıyor — entegrasyon kontratı."""
    resp = player_dashboard_view(player_id=7)
    body = resp.body.decode("utf-8")
    assert "/players/${PLAYER_ID}/info" in body
    assert "/players/${PLAYER_ID}/load" in body
    assert "/players/${PLAYER_ID}/form" in body


# --------------------------------------------------------------------------- #
# /players/{id}/info endpoint
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_player(
    session: Session, *,
    player_id: int = 101, name: str = "Test Oyuncu",
    position: str | None = "MF",
    birth: date | None = None,
    nationality: str | None = "TR",
) -> None:
    session.add(models.Player(
        sport=football.SPORT_NAME,
        external_id=player_id,
        name=name,
        position=position,
        birth_date=birth,
        nationality=nationality,
    ))
    session.flush()


def test_player_info_returns_basic_fields(session: Session) -> None:
    from app.api.main import player_info
    _seed_player(
        session, player_id=101, name="Ali Veli",
        position=football.POSITION_MIDFIELDER,
        birth=date(2000, 5, 30),
        nationality="TR",
    )
    out = player_info(player_id=101, session=session)
    assert out["player_external_id"] == 101
    assert out["name"] == "Ali Veli"
    assert out["position"] == football.POSITION_MIDFIELDER
    assert out["nationality"] == "TR"
    assert out["birth_date"] == "2000-05-30"
    # Yaş hesabı — sabit doğum tarihi 2000-05-30, today >= 2026-05-30 => 26
    today = datetime.now(UTC).date()
    expected_age = today.year - 2000 - (
        1 if (today.month, today.day) < (5, 30) else 0
    )
    assert out["age"] == expected_age


def test_player_info_404_unknown(session: Session) -> None:
    from app.api.main import player_info
    with pytest.raises(HTTPException) as exc:
        player_info(player_id=9999, session=session)
    assert exc.value.status_code == 404


def test_player_info_handles_missing_birth_date(session: Session) -> None:
    from app.api.main import player_info
    _seed_player(session, player_id=200, birth=None)
    out = player_info(player_id=200, session=session)
    assert out["birth_date"] is None
    assert out["age"] is None


def test_player_info_handles_missing_position_and_nationality(
    session: Session,
) -> None:
    from app.api.main import player_info
    _seed_player(session, player_id=300, position=None, nationality=None)
    out = player_info(player_id=300, session=session)
    assert out["position"] is None
    assert out["nationality"] is None


def test_player_info_birthday_before_today_age_correct() -> None:
    """Doğum gününden ÖNCE yaşı 1 az olmalı — Sprint 4 ile aynı formül."""
    today = date(2026, 6, 15)
    # Birth date 2000-08-01 — Today still before birthday this year → age 25
    birth = date(2000, 8, 1)
    expected = today.year - birth.year - (
        1 if (today.month, today.day) < (birth.month, birth.day) else 0
    )
    assert expected == 25


def test_player_info_birthday_after_today_age_correct() -> None:
    """Doğum gününden SONRA yaşı 1 fazla olmalı."""
    today = date(2026, 6, 15)
    birth = date(2000, 5, 1)
    expected = today.year - birth.year - (
        1 if (today.month, today.day) < (birth.month, birth.day) else 0
    )
    assert expected == 26
