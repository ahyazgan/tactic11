"""Sprint 4 backend endpoint'leri — genç/akademi takibi + oyuncu hedefleri
(Faz 5 #37, #38).

- `GET /players/youth` — yaş eşiği altındaki oyuncular + dakika özeti
- `POST /players/{id}/goals` — hedef oluştur
- `GET /players/{id}/goals` — hedef listesi (status filtreli)
- `PATCH /players/{id}/goals/{goal_id}` — status/notes güncelle

Auth protected router'a takılır.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session
from app.sports import football

router = APIRouter(tags=["sprint4"])

DEFAULT_YOUTH_MAX_AGE = 21
VALID_GOAL_STATUSES = ("open", "in_progress", "achieved", "missed")


# --------------------------------------------------------------------------- #
# #37 — Youth players
# --------------------------------------------------------------------------- #


class YouthPlayerOut(BaseModel):
    player_external_id: int
    name: str
    position: str | None
    age: int | None
    matches_played: int
    total_minutes: int


class YouthPlayersOut(BaseModel):
    max_age: int
    team_external_id: int | None
    count: int
    players: list[YouthPlayerOut]


def _age_from_birth(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - (
        1 if (today.month, today.day) < (birth.month, birth.day) else 0
    )


@router.get("/players/youth", response_model=YouthPlayersOut)
def list_youth_players(
    max_age: int = DEFAULT_YOUTH_MAX_AGE,
    team_external_id: int | None = None,
    min_minutes: int = 0,
    session: Session = Depends(get_session),
) -> YouthPlayersOut:
    """Yaş eşiği altındaki oyuncuları listele + appearance özeti.

    `team_external_id` verilirse appearance üzerinden filtre uygulanır
    (Player tablosunda team kolonu yok; PlayerAppearance.team_external_id
    bu eşleştirmeyi sağlar).
    """
    if max_age < 14:
        raise HTTPException(status_code=400, detail="max_age >= 14 olmalı")
    today = datetime.now(UTC).date()

    players = list(session.execute(
        select(models.Player).where(
            models.Player.sport == football.SPORT_NAME,
            models.Player.birth_date.is_not(None),
        )
    ).scalars())

    # Yaş filtresi
    eligible: list[tuple[models.Player, int]] = []
    for p in players:
        age = _age_from_birth(p.birth_date, today)
        if age is None or age > max_age:
            continue
        eligible.append((p, age))
    if not eligible:
        return YouthPlayersOut(
            max_age=max_age, team_external_id=team_external_id,
            count=0, players=[],
        )

    eligible_pids = [p.external_id for p, _ in eligible]
    apps_q = select(models.PlayerAppearance).where(
        models.PlayerAppearance.sport == football.SPORT_NAME,
        models.PlayerAppearance.player_external_id.in_(eligible_pids),
    )
    if team_external_id is not None:
        apps_q = apps_q.where(
            models.PlayerAppearance.team_external_id == team_external_id,
        )
    apps_by_pid: dict[int, list[Any]] = {}
    for a in session.execute(apps_q).scalars():
        apps_by_pid.setdefault(a.player_external_id, []).append(a)

    out: list[YouthPlayerOut] = []
    for p, age in eligible:
        apps = apps_by_pid.get(p.external_id, [])
        # team filtresi varsa: appearance'ı olmayanları gizle
        if team_external_id is not None and not apps:
            continue
        total_min = sum(a.minutes for a in apps)
        if total_min < min_minutes:
            continue
        out.append(YouthPlayerOut(
            player_external_id=p.external_id,
            name=p.name,
            position=p.position,
            age=age,
            matches_played=len(apps),
            total_minutes=total_min,
        ))
    out.sort(key=lambda y: y.total_minutes, reverse=True)

    return YouthPlayersOut(
        max_age=max_age, team_external_id=team_external_id,
        count=len(out), players=out,
    )


# --------------------------------------------------------------------------- #
# #38 — Player goals (CRUD-lite)
# --------------------------------------------------------------------------- #


class GoalPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    metric: str | None = Field(None, max_length=64)
    target_value: float | None = None
    deadline: date | None = None
    notes: str | None = Field(None, max_length=1024)


class GoalUpdatePayload(BaseModel):
    status: str | None = None
    notes: str | None = Field(None, max_length=1024)
    target_value: float | None = None


class GoalOut(BaseModel):
    id: int
    player_external_id: int
    title: str
    metric: str | None
    target_value: float | None
    deadline: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


def _goal_to_out(r: models.PlayerGoal) -> GoalOut:
    return GoalOut(
        id=r.id,
        player_external_id=r.player_external_id,
        title=r.title,
        metric=r.metric,
        target_value=r.target_value,
        deadline=r.deadline,
        status=r.status,
        notes=r.notes,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post("/players/{player_id}/goals", response_model=GoalOut)
def create_goal(
    player_id: int,
    payload: GoalPayload,
    session: Session = Depends(get_session),
) -> GoalOut:
    """Yeni gelişim hedefi oluştur — status default 'open'."""
    now = datetime.now(UTC)
    row = models.PlayerGoal(
        sport=football.SPORT_NAME,
        player_external_id=player_id,
        title=payload.title,
        metric=payload.metric,
        target_value=payload.target_value,
        deadline=payload.deadline,
        status="open",
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    session.commit()
    return _goal_to_out(row)


@router.get("/players/{player_id}/goals", response_model=list[GoalOut])
def list_goals(
    player_id: int,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[GoalOut]:
    """Oyuncunun hedefleri — opsiyonel status filtresi."""
    q = select(models.PlayerGoal).where(
        models.PlayerGoal.sport == football.SPORT_NAME,
        models.PlayerGoal.player_external_id == player_id,
    )
    if status is not None:
        if status not in VALID_GOAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status {status} geçersiz — {VALID_GOAL_STATUSES}",
            )
        q = q.where(models.PlayerGoal.status == status)
    q = q.order_by(models.PlayerGoal.created_at.desc())
    rows = list(session.execute(q).scalars())
    return [_goal_to_out(r) for r in rows]


@router.patch("/players/{player_id}/goals/{goal_id}", response_model=GoalOut)
def update_goal(
    player_id: int,
    goal_id: int,
    payload: GoalUpdatePayload,
    session: Session = Depends(get_session),
) -> GoalOut:
    """Hedef status/notes/target güncelle (kısmi update)."""
    row = session.execute(
        select(models.PlayerGoal).where(
            models.PlayerGoal.id == goal_id,
            models.PlayerGoal.player_external_id == player_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"goal {goal_id} bulunamadı",
        )
    if payload.status is not None:
        if payload.status not in VALID_GOAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status {payload.status} geçersiz — {VALID_GOAL_STATUSES}",
            )
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.target_value is not None:
        row.target_value = payload.target_value
    row.updated_at = datetime.now(UTC)
    session.flush()
    session.commit()
    return _goal_to_out(row)
