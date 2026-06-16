"""Sprint 4 endpoint testleri — youth players + player goals
(Faz 5 #37, #38)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.sprint4 import (
    GoalPayload,
    GoalUpdatePayload,
    create_goal,
    list_goals,
    list_youth_players,
    update_goal,
)
from app.db import models
from app.db.base import Base
from app.sports import football


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_player(
    session: Session, *,
    player_id: int, name: str = "Player",
    position: str | None = None, birth: date | None = None,
) -> None:
    session.add(models.Player(
        sport=football.SPORT_NAME,
        external_id=player_id,
        name=name,
        position=position,
        birth_date=birth,
    ))
    session.flush()


def _seed_appearance(
    session: Session, *,
    player_id: int, match_id: int,
    minutes: int = 90,
    team_id: int | None = None,
) -> None:
    session.add(models.PlayerAppearance(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        match_external_id=match_id,
        team_external_id=team_id,
        minutes=minutes,
        kickoff=datetime.now(UTC),
    ))
    session.flush()


# --------------------------------------------------------------------------- #
# #37 — Youth players
# --------------------------------------------------------------------------- #


def test_youth_players_age_filter(session: Session) -> None:
    today = datetime.now(UTC).date()
    _seed_player(session, player_id=1, name="Genc A",
                 birth=date(today.year - 19, 1, 1))
    _seed_player(session, player_id=2, name="Genc B",
                 birth=date(today.year - 21, 6, 1))
    _seed_player(session, player_id=3, name="Yasli",
                 birth=date(today.year - 28, 1, 1))
    _seed_appearance(session, player_id=1, match_id=10, minutes=90)
    _seed_appearance(session, player_id=2, match_id=11, minutes=45)
    _seed_appearance(session, player_id=3, match_id=12, minutes=90)

    out = list_youth_players(max_age=21, session=session)
    pids = {p.player_external_id for p in out.players}
    assert pids == {1, 2}
    assert out.count == 2
    # Toplam dakikaya göre azalan sıralı
    assert out.players[0].total_minutes >= out.players[1].total_minutes


def test_youth_players_min_minutes(session: Session) -> None:
    today = datetime.now(UTC).date()
    _seed_player(session, player_id=1, birth=date(today.year - 18, 1, 1))
    _seed_player(session, player_id=2, birth=date(today.year - 18, 1, 1))
    _seed_appearance(session, player_id=1, match_id=10, minutes=90)
    _seed_appearance(session, player_id=2, match_id=11, minutes=10)

    out = list_youth_players(max_age=21, min_minutes=60, session=session)
    pids = {p.player_external_id for p in out.players}
    assert pids == {1}


def test_youth_players_team_filter(session: Session) -> None:
    today = datetime.now(UTC).date()
    _seed_player(session, player_id=1, birth=date(today.year - 19, 1, 1))
    _seed_player(session, player_id=2, birth=date(today.year - 19, 1, 1))
    _seed_appearance(session, player_id=1, match_id=10, team_id=11, minutes=90)
    _seed_appearance(session, player_id=2, match_id=20, team_id=22, minutes=90)

    out = list_youth_players(max_age=21, team_external_id=11, session=session)
    pids = {p.player_external_id for p in out.players}
    assert pids == {1}


def test_youth_players_skip_missing_birth_date(session: Session) -> None:
    _seed_player(session, player_id=1, birth=None)  # bilinmeyen yaş atlanır
    out = list_youth_players(max_age=21, session=session)
    assert out.count == 0


def test_youth_players_invalid_max_age(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        list_youth_players(max_age=10, session=session)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# #38 — Player goals CRUD-lite
# --------------------------------------------------------------------------- #


def test_goal_create_then_list(session: Session) -> None:
    payload = GoalPayload(
        title="Pas isabeti %85'e çıksın",
        metric="passes_accuracy",
        target_value=85.0,
        deadline=date.today() + timedelta(days=90),
        notes="Antrenörle haftalık takip",
    )
    out = create_goal(player_id=42, payload=payload, session=session)
    assert out.player_external_id == 42
    assert out.status == "open"
    assert out.metric == "passes_accuracy"

    listed = list_goals(player_id=42, session=session)
    assert len(listed) == 1
    assert listed[0].id == out.id


def test_goal_status_filter(session: Session) -> None:
    p_open = GoalPayload(title="A")
    p_other = GoalPayload(title="B")
    open_goal = create_goal(player_id=1, payload=p_open, session=session)
    other_goal = create_goal(player_id=1, payload=p_other, session=session)
    update_goal(
        player_id=1, goal_id=other_goal.id,
        payload=GoalUpdatePayload(status="achieved"),
        session=session,
    )

    open_only = list_goals(player_id=1, status="open", session=session)
    achieved_only = list_goals(player_id=1, status="achieved", session=session)
    assert [g.id for g in open_only] == [open_goal.id]
    assert [g.id for g in achieved_only] == [other_goal.id]


def test_goal_update_invalid_status_rejected(session: Session) -> None:
    out = create_goal(
        player_id=7, payload=GoalPayload(title="x"), session=session,
    )
    with pytest.raises(HTTPException) as exc:
        update_goal(
            player_id=7, goal_id=out.id,
            payload=GoalUpdatePayload(status="bogus"),
            session=session,
        )
    assert exc.value.status_code == 400


def test_goal_update_unknown_returns_404(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        update_goal(
            player_id=1, goal_id=9999,
            payload=GoalUpdatePayload(status="achieved"),
            session=session,
        )
    assert exc.value.status_code == 404


def test_goal_list_invalid_status_filter_rejected(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        list_goals(player_id=1, status="bogus", session=session)
    assert exc.value.status_code == 400
