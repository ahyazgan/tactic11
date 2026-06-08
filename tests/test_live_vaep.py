"""Canlı VAEP helper + REST endpoint testleri (Faz 5 #47).

`_compute_live_vaep` saf — DB/HTTP yok; sadece event listeleri alır.
REST endpoint DB'den event yükler ve aynı helper'a iletir.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.live import _compute_live_vaep
from app.api.live_vaep import live_vaep_snapshot
from app.db import models
from app.db.base import Base
from app.domain import Carry, PassEvent
from app.sports import football

# --------------------------------------------------------------------------- #
# Saf helper testleri (event-list input, DB yok)
# --------------------------------------------------------------------------- #


def _pass(
    *, minute: float, team_id: int, player_id: int,
    sx: float = 50.0, sy: float = 30.0,
    ex: float = 60.0, ey: float = 30.0,
) -> PassEvent:
    return PassEvent(
        sport="football",
        match_external_id=1,
        possession_id=int(minute * 10),
        team_external_id=team_id,
        player_external_id=player_id,
        minute=minute,
        period=1 if minute <= 45 else 2,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
        completed=True,
    )


def _carry(
    *, minute: float, team_id: int, player_id: int,
    sx: float = 50.0, sy: float = 30.0,
    ex: float = 70.0, ey: float = 30.0,
) -> Carry:
    return Carry(
        sport="football",
        match_external_id=1,
        possession_id=int(minute * 10),
        team_external_id=team_id,
        player_external_id=player_id,
        minute=minute,
        period=1 if minute <= 45 else 2,
        start_x=sx, start_y=sy, end_x=ex, end_y=ey,
    )


def test_live_vaep_empty_input_returns_zero() -> None:
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=[], carries=[], shots=[],
        current_minute=45.0,
    )
    assert out["my_team_total"] == 0.0
    assert out["opp_team_total"] == 0.0
    assert out["my_team_actions"] == 0
    assert out["top_players"] == []


def test_live_vaep_aggregates_team_totals() -> None:
    passes = [
        _pass(minute=5, team_id=11, player_id=101),
        _pass(minute=10, team_id=11, player_id=102),
        _pass(minute=12, team_id=22, player_id=201),
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[],
        current_minute=15.0,
    )
    assert out["my_team_actions"] == 2  # 2 takım-11 pass
    assert out["opp_team_actions"] == 1
    assert out["current_minute"] == 15.0
    assert isinstance(out["my_team_total"], float)


def test_live_vaep_top_players_sorted_descending() -> None:
    # Player 101 — 3 ileri pas (yüksek VAEP)
    # Player 102 — 1 ileri pas (düşük VAEP)
    # Player 103 — 0 aksiyon (filtre dışı)
    passes = [
        _pass(minute=1, team_id=11, player_id=101, sx=40, ex=80),
        _pass(minute=2, team_id=11, player_id=101, sx=40, ex=80),
        _pass(minute=3, team_id=11, player_id=101, sx=40, ex=80),
        _pass(minute=4, team_id=11, player_id=102, sx=40, ex=50),
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[],
        current_minute=10.0, top_n=5,
    )
    ids = [p["player_id"] for p in out["top_players"]]
    assert 101 in ids and 102 in ids
    assert 103 not in ids  # action'sız oyuncu yok
    # 101 daha yüksek VAEP (3 ileri pas)
    p101 = next(p for p in out["top_players"] if p["player_id"] == 101)
    p102 = next(p for p in out["top_players"] if p["player_id"] == 102)
    assert p101["vaep_value"] >= p102["vaep_value"]
    assert p101["total_actions"] == 3


def test_live_vaep_top_n_caps_list() -> None:
    passes = [
        _pass(minute=i, team_id=11, player_id=100 + i)
        for i in range(1, 11)
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[],
        current_minute=15.0, top_n=3,
    )
    assert len(out["top_players"]) == 3


def test_live_vaep_only_my_team_players_listed() -> None:
    passes = [
        _pass(minute=5, team_id=11, player_id=101),
        _pass(minute=6, team_id=22, player_id=201),
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[],
        current_minute=10.0,
    )
    ids = {p["player_id"] for p in out["top_players"]}
    assert ids == {101}
    assert 201 not in ids


def test_live_vaep_includes_carries() -> None:
    passes = [_pass(minute=1, team_id=11, player_id=101)]
    carries = [
        _carry(minute=5, team_id=11, player_id=102),
        _carry(minute=6, team_id=11, player_id=102),
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=carries, shots=[],
        current_minute=10.0,
    )
    ids = {p["player_id"] for p in out["top_players"]}
    assert 102 in ids


def test_live_vaep_model_version_baseline() -> None:
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=[_pass(minute=1, team_id=11, player_id=101)],
        carries=[], shots=[],
        current_minute=10.0,
    )
    assert "baseline" in out["model_version"]


# --------------------------------------------------------------------------- #
# Faz B — kadro farkındalığı: oyuncu-başına dakika normalizasyonu
# --------------------------------------------------------------------------- #


def test_live_vaep_appearances_normalize_per_player_minutes() -> None:
    """Aynı aksiyonu yapan iki oyuncudan az dakika oynayanın VAEP/90'ı yüksek."""
    from app.engine.live_lineup import PlayerAppearance

    # 101 baştan beri oynuyor (75 dk), 102 60'ta girdi (15 dk). İkisi de 1 ileri pas.
    passes = [
        _pass(minute=10, team_id=11, player_id=101, sx=40, ex=80),
        _pass(minute=65, team_id=11, player_id=102, sx=40, ex=80),
    ]
    appearances = [
        PlayerAppearance(101, 11, start_minute=0.0, end_minute=None),
        PlayerAppearance(102, 11, start_minute=60.0, end_minute=None),
    ]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[],
        current_minute=75.0, appearances=appearances,
    )
    by_id = {p["player_id"]: p for p in out["top_players"]}
    assert by_id[101]["minutes_played"] == 75.0
    assert by_id[102]["minutes_played"] == 15.0
    # Aynı tek aksiyon → az dakika oynayan 102'nin per-90'ı belirgin yüksek.
    assert by_id[102]["vaep_per_90"] > by_id[101]["vaep_per_90"]


def test_live_vaep_without_appearances_uses_current_minute() -> None:
    """appearances=None → eski davranış: herkes current_minute'a normalize."""
    passes = [_pass(minute=10, team_id=11, player_id=101, sx=40, ex=80)]
    out = _compute_live_vaep(
        my_team_id=11, opp_team_id=22,
        passes=passes, carries=[], shots=[], current_minute=75.0,
    )
    assert out["top_players"][0]["minutes_played"] == 75.0


# --------------------------------------------------------------------------- #
# REST endpoint testleri
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_match(
    session: Session, *,
    match_id: int = 9100, home_id: int = 11, away_id: int = 22,
) -> None:
    session.add(models.Match(
        sport=football.SPORT_NAME,
        external_id=match_id,
        league_external_id=1,
        season=2024,
        kickoff=datetime.now(UTC),
        status="LIVE",
        home_team_external_id=home_id,
        away_team_external_id=away_id,
    ))
    session.flush()


def test_endpoint_404_unknown_match(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        live_vaep_snapshot(
            match_id=9999, my_team_id=11, session=session,
        )
    assert exc.value.status_code == 404


def test_endpoint_400_team_not_in_match(session: Session) -> None:
    _seed_match(session, match_id=9100, home_id=11, away_id=22)
    with pytest.raises(HTTPException) as exc:
        live_vaep_snapshot(
            match_id=9100, my_team_id=99, session=session,
        )
    assert exc.value.status_code == 400


def test_endpoint_400_invalid_minute(session: Session) -> None:
    _seed_match(session, match_id=9100)
    with pytest.raises(HTTPException) as exc:
        live_vaep_snapshot(
            match_id=9100, my_team_id=11, current_minute=200.0,
            session=session,
        )
    assert exc.value.status_code == 400


def test_endpoint_400_invalid_top_n(session: Session) -> None:
    _seed_match(session, match_id=9100)
    with pytest.raises(HTTPException) as exc:
        live_vaep_snapshot(
            match_id=9100, my_team_id=11, top_n=0, session=session,
        )
    assert exc.value.status_code == 400


def test_endpoint_no_events_returns_info(session: Session) -> None:
    _seed_match(session, match_id=9100)
    out = live_vaep_snapshot(
        match_id=9100, my_team_id=11, current_minute=45.0,
        session=session,
    )
    assert out["info"].startswith("Henüz")
    assert out["my_team_id"] == 11
    assert out["opponent_id"] == 22
