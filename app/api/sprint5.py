"""Sprint 5 backend endpoint'leri — formation matchup + team goals
(Faz 5 #24, #32).

- `POST /formations/matchup` — (my, opp) çifti için tarihsel agregat
- `POST /formations/best-against` — bir rakip formasyona karşı top-N
- `POST  /teams/{id}/goals?season=` — sezon hedefi oluştur
- `GET   /teams/{id}/goals?season=&status=` — hedef listele
- `PATCH /teams/{id}/goals/{goal_id}` — status/notes güncelle

Formation matchup endpoint'leri history records'u request body olarak
alır — Match tablosunda formation kolonu yok, kullanıcı/sistem dış
veriden besler.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_session
from app.engine.formation_matcher.compute import (
    FormationMatchupRecord,
    best_formations_against,
    compute_formation_matchup,
)
from app.sports import football

router = APIRouter(tags=["sprint5"])

VALID_TEAM_GOAL_STATUSES = ("open", "in_progress", "achieved", "missed")


# --------------------------------------------------------------------------- #
# #24 — Formation matchup
# --------------------------------------------------------------------------- #


class FormationRecordIn(BaseModel):
    my_formation: str = Field(..., min_length=3, max_length=16)
    opp_formation: str = Field(..., min_length=3, max_length=16)
    my_goals: int = Field(..., ge=0)
    opp_goals: int = Field(..., ge=0)


class FormationMatchupIn(BaseModel):
    my_formation: str
    opp_formation: str
    records: list[FormationRecordIn]


class FormationMatchupOut(BaseModel):
    my_formation: str
    opp_formation: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    win_rate: float
    avg_goal_diff: float
    avg_my_goals: float
    avg_opp_goals: float


class BestAgainstIn(BaseModel):
    opp_formation: str
    records: list[FormationRecordIn]
    min_matches: int = 3
    top_n: int = 5


def _record_to_dataclass(r: FormationRecordIn) -> FormationMatchupRecord:
    return FormationMatchupRecord(
        my_formation=r.my_formation,
        opp_formation=r.opp_formation,
        my_goals=r.my_goals,
        opp_goals=r.opp_goals,
    )


@router.post("/formations/matchup", response_model=FormationMatchupOut)
def formation_matchup(payload: FormationMatchupIn) -> FormationMatchupOut:
    """Bir (my, opp) formation çifti için tarihsel agregat."""
    records = [_record_to_dataclass(r) for r in payload.records]
    rep = compute_formation_matchup(
        payload.my_formation, payload.opp_formation, records,
    ).value
    return FormationMatchupOut(
        my_formation=rep.my_formation,
        opp_formation=rep.opp_formation,
        matches_played=rep.matches_played,
        wins=rep.wins, draws=rep.draws, losses=rep.losses,
        win_rate=rep.win_rate,
        avg_goal_diff=rep.avg_goal_diff,
        avg_my_goals=rep.avg_my_goals,
        avg_opp_goals=rep.avg_opp_goals,
    )


@router.post("/formations/best-against",
             response_model=list[FormationMatchupOut])
def formations_best_against(payload: BestAgainstIn) -> list[FormationMatchupOut]:
    """Bir rakip formasyona karşı en yüksek win_rate'li top-N kendi formasyonu."""
    records = [_record_to_dataclass(r) for r in payload.records]
    reports = best_formations_against(
        payload.opp_formation, records,
        min_matches=payload.min_matches, top_n=payload.top_n,
    )
    return [
        FormationMatchupOut(
            my_formation=rep.my_formation,
            opp_formation=rep.opp_formation,
            matches_played=rep.matches_played,
            wins=rep.wins, draws=rep.draws, losses=rep.losses,
            win_rate=rep.win_rate,
            avg_goal_diff=rep.avg_goal_diff,
            avg_my_goals=rep.avg_my_goals,
            avg_opp_goals=rep.avg_opp_goals,
        )
        for rep in reports
    ]


# --------------------------------------------------------------------------- #
# #32 — Team season goals (CRUD-lite)
# --------------------------------------------------------------------------- #


class TeamGoalPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    metric: str | None = Field(None, max_length=64)
    target_value: float | None = None
    deadline: date | None = None
    notes: str | None = Field(None, max_length=1024)


class TeamGoalUpdatePayload(BaseModel):
    status: str | None = None
    notes: str | None = Field(None, max_length=1024)
    target_value: float | None = None


class TeamGoalOut(BaseModel):
    id: int
    team_external_id: int
    season: int
    title: str
    metric: str | None
    target_value: float | None
    deadline: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


def _team_goal_to_out(r: models.TeamGoal) -> TeamGoalOut:
    return TeamGoalOut(
        id=r.id,
        team_external_id=r.team_external_id,
        season=r.season,
        title=r.title,
        metric=r.metric,
        target_value=r.target_value,
        deadline=r.deadline,
        status=r.status,
        notes=r.notes,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.post("/teams/{team_id}/goals", response_model=TeamGoalOut)
def create_team_goal(
    team_id: int,
    season: int,
    payload: TeamGoalPayload,
    session: Session = Depends(get_session),
) -> TeamGoalOut:
    """Sezon hedefi oluştur — status default 'open'."""
    now = datetime.now(UTC)
    row = models.TeamGoal(
        sport=football.SPORT_NAME,
        team_external_id=team_id,
        season=season,
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
    return _team_goal_to_out(row)


@router.get("/teams/{team_id}/goals", response_model=list[TeamGoalOut])
def list_team_goals(
    team_id: int,
    season: int | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[TeamGoalOut]:
    """Takım hedefleri — sezon ve status filtreli."""
    q = select(models.TeamGoal).where(
        models.TeamGoal.sport == football.SPORT_NAME,
        models.TeamGoal.team_external_id == team_id,
    )
    if season is not None:
        q = q.where(models.TeamGoal.season == season)
    if status is not None:
        if status not in VALID_TEAM_GOAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status {status} geçersiz — {VALID_TEAM_GOAL_STATUSES}",
            )
        q = q.where(models.TeamGoal.status == status)
    q = q.order_by(models.TeamGoal.created_at.desc())
    rows = list(session.execute(q).scalars())
    return [_team_goal_to_out(r) for r in rows]


@router.patch("/teams/{team_id}/goals/{goal_id}", response_model=TeamGoalOut)
def update_team_goal(
    team_id: int,
    goal_id: int,
    payload: TeamGoalUpdatePayload,
    session: Session = Depends(get_session),
) -> TeamGoalOut:
    """Takım hedefi status/notes/target güncelle (kısmi)."""
    row = session.execute(
        select(models.TeamGoal).where(
            models.TeamGoal.id == goal_id,
            models.TeamGoal.team_external_id == team_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"team goal {goal_id} bulunamadı",
        )
    if payload.status is not None:
        if payload.status not in VALID_TEAM_GOAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status {payload.status} geçersiz — {VALID_TEAM_GOAL_STATUSES}",
            )
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.target_value is not None:
        row.target_value = payload.target_value
    row.updated_at = datetime.now(UTC)
    session.flush()
    session.commit()
    return _team_goal_to_out(row)
